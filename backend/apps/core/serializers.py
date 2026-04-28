from rest_framework import serializers

from .models import (
    BusinessInvestorRelation,
    BusinessRegistrationRequest,
    InvestorInvite,
    Partner,
)


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ['id', 'role', 'display_name', 'is_active', 'user']
        read_only_fields = ['id']


class BusinessInvestorRelationSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_user = serializers.IntegerField(source='partner.user_id', read_only=True)

    class Meta:
        model = BusinessInvestorRelation
        fields = [
            'id', 'partner', 'partner_name', 'partner_user',
            'status', 'source', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class InvestorInviteSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='tenant.name', read_only=True)
    invite_path = serializers.SerializerMethodField()

    class Meta:
        model = InvestorInvite
        fields = [
            'id', 'token', 'email', 'display_name', 'status',
            'business_name', 'expires_at', 'accepted_at', 'accepted_by',
            'invite_path', 'created_at',
        ]
        read_only_fields = [
            'id', 'token', 'status', 'business_name', 'expires_at',
            'accepted_at', 'accepted_by', 'invite_path', 'created_at',
        ]

    def get_invite_path(self, obj):
        return f'/investor/invite/{obj.token}'


class InvestorInviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    display_name = serializers.CharField(required=False, allow_blank=True, default='')
    expires_days = serializers.IntegerField(required=False, default=14, min_value=1, max_value=60)


class InvestorInvitePreviewSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='tenant.name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = InvestorInvite
        fields = [
            'token', 'email', 'display_name', 'status',
            'business_name', 'expires_at', 'is_expired',
        ]


class InvestorInviteRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=4, write_only=True)
    display_name = serializers.CharField(required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')


class BusinessRegistrationRequestSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    approved_business_name = serializers.CharField(source='approved_business.name', read_only=True)

    class Meta:
        model = BusinessRegistrationRequest
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'phone',
            'business_name',
            'status',
            'rejection_reason',
            'reviewed_by',
            'reviewed_at',
            'approved_user',
            'approved_business',
            'approved_business_name',
            'created_at',
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return ' '.join(
            part for part in [obj.first_name.strip(), obj.last_name.strip()] if part
        ).strip()


class BusinessRegistrationRequestCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=32)
    business_name = serializers.CharField(max_length=255)


class BusinessRegistrationRequestRejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default='',
    )
