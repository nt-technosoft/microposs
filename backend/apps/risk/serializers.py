"""
Risk serializers.
"""

from rest_framework import serializers
from .models import RiskEvent, InventoryCheck, InventoryCheckLine


class RiskEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskEvent
        fields = [
            'id', 'event_type', 'lot',
            'quantity', 'monetary_impact',
            'affects_investor', 'negligence',
            'responsible_user', 'reason', 'resolution',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class WriteoffCreateSerializer(serializers.Serializer):
    lot_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField()
    negligence = serializers.BooleanField(default=False)


class InventoryCheckLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='product_variant.__str__', read_only=True,
    )

    class Meta:
        model = InventoryCheckLine
        fields = [
            'id', 'product_variant', 'product_name',
            'expected_quantity', 'actual_quantity', 'difference',
        ]
        read_only_fields = ['id', 'difference']


class InventoryCheckLineInputSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    expected_quantity = serializers.IntegerField(min_value=0)
    actual_quantity = serializers.IntegerField(min_value=0)


class InventoryCheckSerializer(serializers.ModelSerializer):
    lines = InventoryCheckLineSerializer(many=True, read_only=True)
    location_name = serializers.CharField(
        source='location.name', read_only=True,
    )

    class Meta:
        model = InventoryCheck
        fields = [
            'id', 'location', 'location_name',
            'status', 'checked_by',
            'completed_at', 'notes', 'lines',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'completed_at', 'created_at']


class InventoryCheckCreateSerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    lines = InventoryCheckLineInputSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
