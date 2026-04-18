"""
Investors API views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsInvestor

from .models import Investor, InvestorContract
from .serializers import (
    InvestorSerializer, InvestorCreateSerializer,
    InvestorContractSerializer, InvestorContractCreateSerializer,
)
from .services import close_investor_contract, update_investor_summary


class InvestorViewSet(viewsets.ModelViewSet):
    serializer_class = InvestorSerializer
    permission_classes = [IsOwner]
    search_fields = ['name', 'phone']
    ordering = ['name']

    def get_queryset(self):
        return Investor.objects.filter(
            tenant_id=self.request.tenant_id,
        ).prefetch_related('contracts')

    def get_serializer_class(self):
        if self.action == 'create':
            return InvestorCreateSerializer
        return InvestorSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvestorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        investor = Investor.objects.create(
            tenant_id=request.tenant_id,
            user_id=data['user_id'],
            name=data['name'],
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            notes=data.get('notes', ''),
        )
        return Response(InvestorSerializer(investor).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.soft_delete()


class InvestorContractViewSet(viewsets.ModelViewSet):
    serializer_class = InvestorContractSerializer
    permission_classes = [IsOwner]
    ordering = ['-start_date']

    def get_queryset(self):
        qs = InvestorContract.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('investor')

        investor_id = self.request.query_params.get('investor')
        if investor_id:
            qs = qs.filter(investor_id=investor_id)

        contract_status = self.request.query_params.get('status')
        if contract_status:
            qs = qs.filter(status=contract_status)

        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return InvestorContractCreateSerializer
        return InvestorContractSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvestorContractCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        contract = InvestorContract.objects.create(
            tenant_id=request.tenant_id,
            investor_id=data['investor_id'],
            contract_type=data['contract_type'],
            default_profit_ratio=data['default_profit_ratio'],
            start_date=data['start_date'],
            notes=data.get('notes', ''),
            status='active',
        )
        return Response(InvestorContractSerializer(contract).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        contract = self.get_object()
        contract = close_investor_contract(
            tenant_id=request.tenant_id,
            contract_id=contract.pk,
        )
        return Response(InvestorContractSerializer(contract).data)

    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        """
        Computed investor summary for this contract.
        Backed by PartnerLedgerEntry — replaces deprecated InvestorSummary model.
        """
        contract = self.get_object()
        data = update_investor_summary(
            tenant_id=request.tenant_id,
            contract_id=contract.pk,
        )
        return Response(data)
