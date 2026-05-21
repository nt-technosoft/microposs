from django.contrib.auth.models import Group, User
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.permissions import IsOwner, IsPlatformAdmin

from .models import (
    BusinessInvestorRelation,
    BusinessRegistrationRequest,
    InvestorInvite,
    Partner,
)
from .serializers import (
    BusinessInvestorRelationSerializer,
    BusinessRegistrationRequestCreateSerializer,
    BusinessRegistrationRequestRejectSerializer,
    BusinessRegistrationRequestSerializer,
    InvestorInviteCreateSerializer,
    InvestorInvitePreviewSerializer,
    InvestorInviteRegisterSerializer,
    InvestorInviteSerializer,
    PartnerSerializer,
)
from .services import (
    accept_investor_invite,
    approve_business_registration_request,
    create_business_registration_request,
    create_investor_invite,
    reject_business_registration_request,
)


class PartnerViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PartnerSerializer
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'head', 'options']
    ordering = ['role', 'display_name']

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def get_queryset(self):
        queryset = Partner.objects.filter(tenant_id=self.request.tenant_id)

        role = self.request.query_params.get('role')
        if role == Partner.Role.INVESTOR:
            queryset = queryset.filter(
                role=Partner.Role.INVESTOR,
                investor_relations__status=BusinessInvestorRelation.Status.ACTIVE,
            )
        elif role:
            queryset = queryset.filter(role=role)
        else:
            active_investors = BusinessInvestorRelation.objects.filter(
                tenant_id=self.request.tenant_id,
                status=BusinessInvestorRelation.Status.ACTIVE,
            ).values('partner_id')
            queryset = queryset.filter(
                Q(role=Partner.Role.OPERATOR) | Q(id__in=active_investors),
            )

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(
                is_active=str(is_active).lower() not in ('false', '0', 'no'),
            )

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(display_name__icontains=search)

        return queryset


class BusinessInvestorRelationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BusinessInvestorRelationSerializer
    permission_classes = [IsOwner]
    ordering = ['-created_at']

    def get_queryset(self):
        return (
            BusinessInvestorRelation.objects
            .filter(tenant_id=self.request.tenant_id)
            .select_related('partner', 'partner__user')
        )


class InvestorInviteViewSet(viewsets.ModelViewSet):
    serializer_class = InvestorInviteSerializer
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'head', 'options']
    ordering = ['-created_at']

    def get_queryset(self):
        return InvestorInvite.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('tenant', 'accepted_by')

    def create(self, request, *args, **kwargs):
        serializer = InvestorInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = create_investor_invite(
            tenant_id=request.tenant_id,
            invited_by_id=request.user.id,
            **serializer.validated_data,
        )
        return Response(InvestorInviteSerializer(invite).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, request, pk=None):
        invite = self.get_object()
        if invite.status == InvestorInvite.Status.PENDING:
            invite.status = InvestorInvite.Status.REVOKED
            invite.save(update_fields=['status', 'updated_at'])
        return Response(InvestorInviteSerializer(invite).data)


class InvestorInvitePreviewView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        invite = get_object_or_404(
            InvestorInvite.objects.select_related('tenant'),
            token=token,
        )
        return Response(InvestorInvitePreviewSerializer(invite).data)


class InvestorInviteAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        try:
            invite, relation = accept_investor_invite(
                token=token,
                user=request.user,
                display_name=str(request.data.get('display_name', '')).strip(),
            )
        except InvestorInvite.DoesNotExist as error:
            raise ValidationError({'detail': 'Invite not found.'}) from error
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response({
            'invite': InvestorInviteSerializer(invite).data,
            'relation': BusinessInvestorRelationSerializer(relation).data,
        })


class InvestorInviteRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, token):
        serializer = InvestorInviteRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(username=data['username']).exists():
            raise ValidationError({'username': 'Username already exists.'})

        user = User.objects.create_user(
            username=data['username'],
            email=(data.get('email') or '').strip(),
            password=data['password'],
        )
        group, _ = Group.objects.get_or_create(name='investor')
        user.groups.add(group)

        try:
            invite, relation = accept_investor_invite(
                token=token,
                user=user,
                display_name=data.get('display_name', ''),
            )
        except InvestorInvite.DoesNotExist as error:
            user.delete()
            raise ValidationError({'detail': 'Invite not found.'}) from error
        except ValueError as error:
            user.delete()
            raise ValidationError({'detail': str(error)}) from error

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'invite': InvestorInviteSerializer(invite).data,
            'relation': BusinessInvestorRelationSerializer(relation).data,
        }, status=status.HTTP_201_CREATED)


class BusinessRegistrationRequestViewSet(viewsets.GenericViewSet):
    queryset = BusinessRegistrationRequest.objects.all()
    serializer_class = BusinessRegistrationRequestSerializer
    ordering = ['created_at']

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsPlatformAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = (
            BusinessRegistrationRequest.objects
            .select_related('reviewed_by', 'approved_user', 'approved_business')
            .order_by('status', '-created_at')
        )
        status_filter = str(self.request.query_params.get('status', '')).strip().upper()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = BusinessRegistrationRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            registration_request = create_business_registration_request(**serializer.validated_data)
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(
            BusinessRegistrationRequestSerializer(registration_request).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        registration_request = self.get_object()
        try:
            registration_request = approve_business_registration_request(
                request_id=registration_request.pk,
                reviewed_by=request.user,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        serializer = self.get_serializer(registration_request)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        payload = BusinessRegistrationRequestRejectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        registration_request = self.get_object()
        try:
            registration_request = reject_business_registration_request(
                request_id=registration_request.pk,
                reviewed_by=request.user,
                rejection_reason=payload.validated_data['rejection_reason'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        serializer = self.get_serializer(registration_request)
        return Response(serializer.data)
