"""Custom exceptions for MicroPOS business logic."""

from rest_framework.exceptions import APIException
from rest_framework import status


class ImmutableRecordError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This record is immutable and cannot be modified.'
    default_code = 'immutable_record'


class InsufficientStockError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Not enough stock available.'
    default_code = 'insufficient_stock'


class DuplicateRequestError(APIException):
    status_code = status.HTTP_200_OK
    default_detail = 'This request has already been processed.'
    default_code = 'duplicate_request'


class ContractCloseError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot close contract with active lots.'
    default_code = 'contract_close_error'


class InvalidParticipantRatioError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Participant profit ratios must sum to 1.0.'
    default_code = 'invalid_ratio'


class CreditSaleRequiresCustomerError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Credit sales require a customer.'
    default_code = 'customer_required'


class PricingModeViolationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Sale line does not match product pricing mode.'
    default_code = 'pricing_mode_violation'


class InvalidUnitPriceError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Unit price must be a positive number.'
    default_code = 'invalid_unit_price'


class DiscountReasonRequiredError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Discount reason is required when sale price differs from base price.'
    default_code = 'discount_reason_required'


class InvalidDiscountReasonError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Discount reason is invalid or inactive.'
    default_code = 'discount_reason_invalid'
