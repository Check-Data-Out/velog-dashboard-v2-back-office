"""
AWS SES API 에러 코드를 그룹화하여 관리합니다.
Common API 에러 코드 참고:
    https://docs.aws.amazon.com/ses/latest/APIReference/CommonErrors.html
"""

AWS_AUTH_ERROR_CODES = {
    # Common
    "InvalidClientTokenId",
    "AccessDeniedException",
    "MissingAuthenticationToken",
    "IncompleteSignature",
    "NotAuthorized",
    "AccessDenied",
    # SES
    "SignatureDoesNotMatch",
}

AWS_VALUE_ERROR_CODES = {
    # Common
    "InvalidParameterCombination",
    "InvalidParameterValue",
    "InvalidQueryParameter",
    "MalformedQueryString",
    "MissingParameter",
    "ValidationError",
}

AWS_LIMIT_ERROR_CODES = {
    # Common
    "ThrottlingException",
    "TooManyRequestsException",
    # SES
    "LimitExceededException",
}

AWS_SERVICE_ERROR_CODES = {
    # Common
    "ServiceUnavailable",
    "InternalFailure",
    "InternalServerError",
}
