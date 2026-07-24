# EcommerceBackend/core/exception.py
from rest_framework.views import exception_handler


# def custom_exception_handler(exc, context):
#     response = exception_handler(exc, context)

#     if response is None:
#         return response

#     return response


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    message = "Validation failed."

    if isinstance(response.data, dict):
        if "detail" in response.data:
            message = response.data["detail"]
        else:
            first_error = next(iter(response.data.values()), None)

            if isinstance(first_error, list) and first_error:
                message = first_error[0]
            elif isinstance(first_error, str):
                message = first_error

    response.data = {
        "success": False,
        "message": message,
        "errors": response.data,
    }

    return response
