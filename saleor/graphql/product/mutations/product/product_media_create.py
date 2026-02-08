import mimetypes

import graphene
from django.core.exceptions import ValidationError
from django.core.files import File

from .....core.http_client import HTTPClient
from .....core.utils.validators import get_oembed_data
from .....permission.enums import ProductPermissions
from .....product import ProductMediaTypes, models
from .....product.error_codes import ProductErrorCode
from .....thumbnail.utils import get_filename_from_url
from .....utils import OC_logger
from ....core import ResolveInfo
from ....core.context import ChannelContext
from ....core.doc_category import DOC_CATEGORY_PRODUCTS
from ....core.mutations import BaseMutation
from ....core.types import BaseInputObjectType, ProductError, Upload
from ....core.validators.file import clean_image_file, is_image_url, validate_image_url
from ....plugins.dataloaders import get_plugin_manager_promise
from ...types import Product, ProductMedia
from ...utils import ALT_CHAR_LIMIT

logger = OC_logger.oc_log("product_media_create")


class ProductMediaCreateInput(BaseInputObjectType):
    alt = graphene.String(description="Alt text for a product media.")
    image = Upload(
        required=False, description="Represents an image file in a multipart request."
    )
    product = graphene.ID(
        required=True, description="ID of an product.", name="product"
    )
    media_url = graphene.String(
        required=False, description="Represents an URL to an external media."
    )

    class Meta:
        doc_category = DOC_CATEGORY_PRODUCTS


class ProductMediaCreate(BaseMutation):
    product = graphene.Field(Product)
    media = graphene.Field(ProductMedia)

    class Arguments:
        input = ProductMediaCreateInput(
            required=True, description="Fields required to create a product media."
        )

    class Meta:
        description = (
            "Create a media object (image or video URL) associated with product. "
            "For image, this mutation must be sent as a `multipart` request. "
            "More detailed specs of the upload format can be found here: "
            "https://github.com/jaydenseric/graphql-multipart-request-spec"
        )
        doc_category = DOC_CATEGORY_PRODUCTS
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
        error_type_field = "product_errors"

    @classmethod
    def validate_input(cls, data):
        image = data.get("image")
        media_url = data.get("media_url")
        alt = data.get("alt")

        if not image and not media_url:
            raise ValidationError(
                {
                    "input": ValidationError(
                        "Image or external URL is required.",
                        code=ProductErrorCode.REQUIRED.value,
                    )
                }
            )
        if image and media_url:
            raise ValidationError(
                {
                    "input": ValidationError(
                        "Either image or external URL is required.",
                        code=ProductErrorCode.DUPLICATED_INPUT_ITEM.value,
                    )
                }
            )

        if alt and len(alt) > ALT_CHAR_LIMIT:
            raise ValidationError(
                {
                    "input": ValidationError(
                        f"Alt field exceeds the character limit of {ALT_CHAR_LIMIT}.",
                        code=ProductErrorCode.INVALID.value,
                    )
                }
            )

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, input
    ):
        cls.validate_input(input)
        product = cls.get_node_or_error(
            info,
            input["product"],
            field="product",
            only_type=Product,
            qs=models.Product.objects.all(),
        )

        alt = input.get("alt", "")
        media_url = input.get("media_url")
        media = None
        if img_data := input.get("image"):
            input["image"] = info.context.FILES.get(img_data)
            image_data = clean_image_file(input, "image", ProductErrorCode)
            media = product.media.create(
                image=image_data, alt=alt, type=ProductMediaTypes.IMAGE
            )
        if media_url:
            # Remote URLs can point to the images or oembed data.
            # In case of images, file is downloaded. Otherwise we keep only
            # URL to remote media.
            guessed_type = mimetypes.guess_type(media_url)[0]
            is_image = is_image_url(media_url)
            logger.info(f"ProductMediaCreate: media_url={media_url}, guessed_type={guessed_type}, is_image_url={is_image}")

            if is_image:
                logger.debug(f"ProductMediaCreate: processing as image URL")
                try:
                    validate_image_url(
                        media_url, "media_url", ProductErrorCode.INVALID.value
                    )
                except Exception as e:
                    logger.error(f"ProductMediaCreate: validate_image_url failed: {e}", exc_info=True)
                    raise

                filename = get_filename_from_url(media_url)
                logger.debug(f"ProductMediaCreate: downloading image, filename={filename}")

                try:
                    image_data = HTTPClient.send_request(
                        "GET", media_url, stream=True, allow_redirects=True,
                        headers={"ngrok-skip-browser-warning": "true"}
                    )
                    logger.debug(f"ProductMediaCreate: download response status={image_data.status_code}")
                except Exception as e:
                    logger.error(f"ProductMediaCreate: image download failed: {e}", exc_info=True)
                    raise

                image_file = File(image_data.raw, filename)
                media = product.media.create(
                    image=image_file,
                    alt=alt,
                    type=ProductMediaTypes.IMAGE,
                )
                logger.info(f"ProductMediaCreate: image saved successfully, media_id={media.pk}")
            else:
                logger.debug(f"ProductMediaCreate: processing as oembed URL")
                try:
                    oembed_data, media_type = get_oembed_data(media_url, "media_url")
                except Exception as e:
                    logger.error(f"ProductMediaCreate: get_oembed_data failed for url={media_url}: {e}", exc_info=True)
                    raise
                media = product.media.create(
                    external_url=oembed_data["url"],
                    alt=oembed_data.get("title", alt),
                    type=media_type,
                    oembed_data=oembed_data,
                )
        manager = get_plugin_manager_promise(info.context).get()
        cls.call_event(manager.product_updated, product)
        cls.call_event(manager.product_media_created, media)
        product = ChannelContext(node=product, channel_slug=None)
        return ProductMediaCreate(product=product, media=media)
