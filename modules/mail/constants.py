"""
AWS SES API 에러 코드를 그룹화하여 관리합니다.
Common API 에러 코드 참고:
    https://docs.aws.amazon.com/ses/latest/APIReference-V2/CommonErrors.html
SES v2 SendEmail 에러 코드 참고:
    https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_SendEmail.html
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
    # SES v2 SendEmail
    "BadRequestException",
    "NotFoundException",
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

# SES v2 SendEmail 에서 발송 자체가 거부된 경우. SendError 로 변환한다
AWS_SEND_REJECTED_ERROR_MESSAGES = {
    "MessageRejected": "이메일이 거부되었습니다.",
    "SendingPausedException": "계정의 이메일 발송이 일시 중지되었습니다.",
    "AccountSuspendedException": "계정의 이메일 발송이 정지되었습니다.",
    "MailFromDomainNotVerifiedException": "MAIL FROM 도메인이 검증되지 않았습니다.",
}
