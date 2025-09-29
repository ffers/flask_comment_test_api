from .views import GraphQLView


def process_view(self, request, view_func, *args):
    if hasattr(view_func, "view_class") and issubclass(
        view_func.view_class, GraphQLView
    ):
        request._graphql_view = True


import logging
import json

logger = logging.getLogger("graphql")

class GraphQLLoggingMiddleware:
    def resolve(self, next, root, info, **args):
        # Логуємо назву поля/мутації та аргументи
        logger.warning(
            f"GraphQL request: {info.parent_type.name}.{info.field_name} "
            f"args={args}"
        )
        result = next(root, info, **args)

        # Якщо результат промісоподібний — обробимо після виконання
        if hasattr(result, "then"):
            def log_result(res):
                try:
                    logger.warning(
                        f"GraphQL response for {info.field_name}: "
                        f"{json.dumps(res, default=str)[:500]}"
                    )
                except Exception as e:
                    logger.error(f"GraphQL logging error: {e}")
                return res
            return result.then(log_result)

        # Якщо одразу є результат
        try:
            logger.warning(
                f"GraphQL response for {info.field_name}: "
                f"{json.dumps(result, default=str)[:500]}"
            )
        except Exception:
            pass

        return result
