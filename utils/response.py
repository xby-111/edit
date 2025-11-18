from fastapi.responses import JSONResponse

def success_response(data=None, message="Success", status_code=200):
    """
    Helper function to create a success response
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "message": message,
            "data": data
        }
    )

def error_response(message="Error occurred", status_code=400, errors=None):
    """
    Helper function to create an error response
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
            "errors": errors or []
        }
    )