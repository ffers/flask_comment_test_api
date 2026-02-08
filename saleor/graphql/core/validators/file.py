import mimetypes
import os

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

from ....core.http_client import HTTPClient
from ....thumbnail import MIME_TYPE_TO_PIL_IDENTIFIER
from ....thumbnail.utils import ProcessedImage
from ....utils import OC_logger
from ..utils import add_hash_to_file_name

Image.init()

logger = OC_logger.oc_log("file_validators")


def is_image_mimetype(mimetype: str) -> bool:
    """Check if mimetype is image."""
    if mimetype is None:
        return False
    return mimetype.startswith("image/")


def is_supported_image_mimetype(mimetype: str) -> bool:
    """Check if mimetype is a mimetype that thumbnails support."""
    if mimetype is None:
        return False
    return mimetype in MIME_TYPE_TO_PIL_IDENTIFIER.keys()


def is_image_url(url: str) -> bool:
    """Check if file URL seems to be an image."""
    filetype = mimetypes.guess_type(url)[0]
    result = filetype is not None and is_image_mimetype(filetype)
    logger.debug(f"is_image_url: url={url}, guessed_type={filetype}, result={result}")
    return result


def validate_image_url(url: str, field_name: str, error_code: str) -> None:
    """Check if remote file has content type of image.

    Instead of the whole file, only the headers are fetched.
    """
    logger.debug(f"validate_image_url: starting validation for url={url}")
    try:
        head = HTTPClient.send_request(
            "HEAD", url, allow_redirects=True,
            headers={"ngrok-skip-browser-warning": "true"}
        )
        logger.debug(f"validate_image_url: HEAD response status={head.status_code}, headers={dict(head.headers)}")
    except Exception as e:
        logger.error(f"validate_image_url: HEAD request failed for url={url}, error={e}")
        raise ValidationError(
            {field_name: ValidationError(f"Failed to fetch image: {e}", code=error_code)}
        )

    header = head.headers
    content_type = header.get("content-type")
    logger.debug(f"validate_image_url: raw content_type={content_type}")

    # Extract MIME type without parameters (e.g., "image/webp; charset=utf-8" -> "image/webp")
    if content_type:
        content_type = content_type.split(";")[0].strip()

    logger.debug(f"validate_image_url: cleaned content_type={content_type}, is_supported={is_supported_image_mimetype(content_type) if content_type else False}")

    if content_type is None or not is_supported_image_mimetype(content_type):
        logger.error(f"validate_image_url: Invalid file type for url={url}, content_type={content_type}")
        raise ValidationError(
            {field_name: ValidationError("Invalid file type.", code=error_code)}
        )

    logger.info(f"validate_image_url: validation passed for url={url}, content_type={content_type}")


def clean_image_file(cleaned_input, img_field_name, error_class):
    """Extract and clean uploaded image file.

    Validate if the file is an image supported by thumbnails.
    """
    img_file = cleaned_input.get(img_field_name)
    if not img_file:
        raise ValidationError(
            {
                img_field_name: ValidationError(
                    "File is required.", code=error_class.REQUIRED
                )
            }
        )
    if not is_supported_image_mimetype(img_file.content_type):
        raise ValidationError(
            {
                img_field_name: ValidationError(
                    "Invalid file type.", code=error_class.INVALID
                )
            }
        )

    _validate_image_format(img_file, img_field_name, error_class)
    try:
        with Image.open(img_file) as image:
            _validate_image_exif(image, img_field_name, error_class)
            img_file.seek(0)
    except (SyntaxError, TypeError, UnidentifiedImageError) as e:
        raise ValidationError(
            {
                img_field_name: ValidationError(
                    "Invalid file. The following error was raised during the attempt "
                    f"of opening the file: {str(e)}",
                    code=error_class.INVALID.value,
                )
            }
        ) from e

    try:
        # validate if the image MIME type is supported
        ProcessedImage.get_image_metadata_from_file(img_file)
    except ValueError as e:
        raise ValidationError(
            {img_field_name: ValidationError(str(e), code=error_class.INVALID.value)}
        ) from e

    add_hash_to_file_name(img_file)
    return img_file


def _validate_image_format(file, field_name, error_class):
    """Validate image file format."""
    allowed_extensions = _get_allowed_extensions()
    _file_name, format = os.path.splitext(file._name)
    if not format:
        raise ValidationError(
            {
                field_name: ValidationError(
                    "Lack of file extension.", code=error_class.INVALID
                )
            }
        )
    if format.lower() not in allowed_extensions:
        raise ValidationError(
            {
                field_name: ValidationError(
                    "Invalid file extension. Image file required.",
                    code=error_class.INVALID,
                )
            }
        )


def _get_allowed_extensions():
    """Return image extension lists that are supported by thumbnails."""
    return [
        ext.lower()
        for ext, file_type in Image.EXTENSION.items()
        if file_type.upper() in MIME_TYPE_TO_PIL_IDENTIFIER.values()
    ]


def _validate_image_exif(img, field_name, error_class):
    try:
        img.getexif()
    except (SyntaxError, TypeError, UnidentifiedImageError) as e:
        raise ValidationError(
            {
                field_name: ValidationError(
                    "Invalid file. The following error was raised during the attempt "
                    f"of getting the exchangeable image file data: {str(e)}.",
                    code=error_class.INVALID.value,
                )
            }
        ) from e
