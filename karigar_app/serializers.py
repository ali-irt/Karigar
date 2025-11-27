"""
Advanced Django REST Framework Serializers for eMechanics
Production-ready serializers with:
- Nested serialization
- Custom validation
- Read/Write field separation
- Dynamic field selection
- Permission-aware serialization
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from .models import (
    User, Mechanic, ServiceRequest, Review, ChatMessage, Transaction,
    Wallet, Promotion, UserPreference, DeviceToken, LocationUpdate,
    ServiceRequestAttachment, ReviewResponse, MechanicDocument,
    Vehicle, ServiceType, MechanicService, ServiceRequestItem, Career
)


# ============================================================================
# BASE SERIALIZERS
# ============================================================================

class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that allows dynamic field selection via query params.
    Usage: /api/users/?fields=id,email,first_name
    """
    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop('fields', None)
        
        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields.split(','))
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)


# ============================================================================
# USER AUTHENTICATION SERIALIZERS
# ============================================================================

class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone', 'role'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
        }
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Password fields didn't match."
            })
        return attrs
    
    def validate_role(self, value):
        """Ensure only customer and mechanic roles can be registered."""
        if value not in ['customer', 'mechanic']:
            raise serializers.ValidationError(
                "Only 'customer' and 'mechanic' roles are allowed during registration."
            )
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        
        # Create mechanic profile if role is mechanic
        if user.role == 'mechanic':
            Mechanic.objects.create(
                user=user,
             )
        
        return user
class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError(
                'Must include "email" and "password".'
            )

        # IMPORT YOUR USER MODEL
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid email or password.')

        # Check password manually
        if not user.check_password(password):
            raise serializers.ValidationError('Invalid email or password.')

        # Check active
        if not user.is_active:
            raise serializers.ValidationError('User account is disabled.')

        # Check suspended
        if getattr(user, "is_suspended", False):
            raise serializers.ValidationError(
                f'Account is suspended. Reason: {user.suspension_reason}'
            )

        attrs['user'] = user
        return attrs



class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "Password fields didn't match."
            })
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


# ============================================================================
# USER SERIALIZERS
# ============================================================================

class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for user preferences."""
    class Meta:
        model = UserPreference
        exclude = ['id', 'user', 'created_at', 'updated_at']


class DeviceTokenSerializer(serializers.ModelSerializer):
    """Serializer for device tokens."""
    class Meta:
        model = DeviceToken
        fields = ['id', 'token', 'device_type', 'device_name', 'is_active']
        read_only_fields = ['id', 'is_active']


class UserSerializer(DynamicFieldsModelSerializer):
    """Comprehensive user serializer."""
    preferences = UserPreferenceSerializer(read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'role_display', 'profile_picture', 'is_verified',
            'is_suspended', 'profile_completion_percentage', 'preferred_language',
            'timezone', 'total_requests', 'total_completed', 'total_cancelled',
            'created_at', 'preferences'
        ]
        read_only_fields = [
            'id', 'is_verified', 'is_suspended', 'profile_completion_percentage',
            'total_requests', 'total_completed', 'total_cancelled', 'created_at'
        ]
        extra_kwargs = {
            'email': {'required': False},
        }


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone', 'profile_picture',
            'preferred_language', 'timezone'
        ]


# ============================================================================
# MECHANIC SERIALIZERS
# ============================================================================

class MechanicDocumentSerializer(serializers.ModelSerializer):
    """Serializer for mechanic documents."""
    class Meta:
        model = MechanicDocument
        fields = ['id', 'document_type', 'document_file', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


class MechanicSerializer(DynamicFieldsModelSerializer):
    """Comprehensive mechanic serializer."""
    user = UserSerializer(read_only=True)
    documents = MechanicDocumentSerializer(many=True, read_only=True)
    distance_km = serializers.FloatField(read_only=True, required=False)
    is_license_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Mechanic
        fields = [
            'id', 'user', 'specializations',
            'years_of_experience', 'bio', 'average_rating', 'total_reviews',
            'is_available', 'current_latitude', 'current_longitude',
            'service_radius_km', 'total_earnings', 'total_services_completed',
            'total_services_cancelled', 'acceptance_rate', 'completion_rate',
            'is_verified', 'verification_date', 'documents', 'distance_km',
            'is_license_valid', 'created_at'
        ]
        read_only_fields = [
            'id', 'average_rating', 'total_reviews', 'total_earnings',
            'total_services_completed', 'total_services_cancelled',
            'acceptance_rate', 'completion_rate', 'is_verified',
            'verification_date', 'created_at'
        ]


class MechanicUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating mechanic profile."""
    class Meta:
        model = Mechanic
        fields = [
         'specializations',
            'years_of_experience', 'bio', 'is_available',
            'service_radius_km'
        ]
    
   



class MechanicServiceSerializer(serializers.ModelSerializer):
    """Serializer for mechanic service offerings."""
    service_type_name = serializers.CharField(source='service_type.name', read_only=True)
    service_type_description = serializers.CharField(
        source='service_type.description',
        read_only=True
    )
    effective_price = serializers.SerializerMethodField()
    
    class Meta:
        model = MechanicService
        fields = [
            'id', 'service_type', 'service_type_name', 'service_type_description',
            'custom_price', 'effective_price', 'is_available', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_effective_price(self, obj):
        """Return custom price if set, otherwise base price."""
        return obj.custom_price if obj.custom_price else obj.service_type.base_price


# ============================================================================
# SERVICE REQUEST SERIALIZERS
# ============================================================================

class ServiceRequestAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for service request attachments."""
    uploaded_by_name = serializers.CharField(
        source='uploaded_by.get_full_name',
        read_only=True
    )
    
    class Meta:
        model = ServiceRequestAttachment
        fields = [
            'id', 'file', 'file_type', 'uploaded_by', 'uploaded_by_name',
            'description', 'created_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'created_at']


class ServiceRequestItemSerializer(serializers.ModelSerializer):
    """Serializer for service request items (parts and labor)."""
    total_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = ServiceRequestItem
        fields = [
            'id', 'description', 'quantity', 'unit_price',
            'total_price', 'item_type', 'is_completed', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ServiceRequestSerializer(DynamicFieldsModelSerializer):
    """Comprehensive service request serializer."""
    customer = UserSerializer(read_only=True)
    mechanic = MechanicSerializer(read_only=True)
    attachments = ServiceRequestAttachmentSerializer(many=True, read_only=True)
    items = ServiceRequestItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True, required=False)
    
    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'customer', 'mechanic', 'service_type', 'description',
            'priority', 'priority_display', 'customer_latitude', 'customer_longitude',
            'service_address', 'status', 'status_display', 'estimated_arrival_time',
            'actual_arrival_time', 'start_time', 'completion_time',
            'estimated_cost', 'actual_cost', 'discount_amount', 'tax_amount',
            'final_amount', 'notes', 'cancellation_reason', 'cancelled_by',
            'attachments', 'items', 'duration_minutes', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'customer', 'mechanic', 'status', 'estimated_arrival_time',
            'actual_arrival_time', 'start_time', 'completion_time',
            'actual_cost', 'final_amount', 'cancellation_reason',
            'cancelled_by', 'created_at', 'updated_at'
        ]


class ServiceRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating service requests."""
    class Meta:
        model = ServiceRequest
        fields = [
            'service_type', 'description', 'priority', 'customer_latitude',
            'customer_longitude', 'service_address', 'estimated_cost', 'notes'
        ]
    
    def validate(self, attrs):
        # Validate customer can request service
        user = self.context['request'].user
        if not user.can_request_service():
            raise serializers.ValidationError(
                "Your account is not eligible to request services."
            )
        return attrs
    
    @transaction.atomic
    def create(self, validated_data):
        validated_data['customer'] = self.context['request'].user
        return super().create(validated_data)


class ServiceRequestUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating service requests."""
    class Meta:
        model = ServiceRequest
        fields = ['description', 'priority', 'service_address', 'notes']


class ServiceRequestAcceptSerializer(serializers.Serializer):
    """Serializer for accepting service requests."""
    estimated_arrival_minutes = serializers.IntegerField(
        min_value=1,
        max_value=180,
        required=True
    )
    
    def validate(self, attrs):
        service_request = self.context['service_request']
        user = self.context['request'].user
        
        if service_request.status != 'pending':
            raise serializers.ValidationError("This request is not available.")
        
        if not user.can_accept_service():
            raise serializers.ValidationError(
                "Your account is not eligible to accept services."
            )
        
        return attrs


class ServiceRequestCompleteSerializer(serializers.Serializer):
    """Serializer for completing service requests."""
    actual_cost = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01')
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class ServiceRequestCancelSerializer(serializers.Serializer):
    """Serializer for cancelling service requests."""
    reason = serializers.CharField(required=True, min_length=10)


# ============================================================================
# REVIEW SERIALIZERS
# ============================================================================

class ReviewResponseSerializer(serializers.ModelSerializer):
    """Serializer for review responses."""
    responder_name = serializers.CharField(
        source='responder.get_full_name',
        read_only=True
    )
    
    class Meta:
        model = ReviewResponse
        fields = ['id', 'responder', 'responder_name', 'response_text', 'created_at']
        read_only_fields = ['id', 'responder', 'created_at']


class ReviewSerializer(DynamicFieldsModelSerializer):
    """Comprehensive review serializer."""
    reviewer = UserSerializer(read_only=True)
    reviewee = UserSerializer(read_only=True)
    service_request_id = serializers.UUIDField(source='service_request.id', read_only=True)
    review_type_display = serializers.CharField(
        source='get_review_type_display',
        read_only=True
    )
    response = ReviewResponseSerializer(read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'service_request_id', 'reviewer', 'reviewee',
            'review_type', 'review_type_display', 'rating',
            'quality_rating', 'punctuality_rating', 'communication_rating',
            'comment', 'is_anonymous', 'helpful_count', 'response', 'created_at'
        ]
        read_only_fields = [
            'id', 'reviewer', 'reviewee', 'review_type', 'helpful_count',
            'created_at'
        ]


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating reviews."""
    class Meta:
        model = Review
        fields = [
            'service_request', 'rating', 'quality_rating',
            'punctuality_rating', 'communication_rating', 'comment',
            'is_anonymous'
        ]
    
    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value
    
    def validate_service_request(self, value):
        user = self.context['request'].user
        
        # Check if service is completed
        if value.status != 'completed':
            raise serializers.ValidationError(
                "Can only review completed service requests."
            )
        
        # Check if user is part of this service
        if value.customer != user and value.mechanic != user:
            raise serializers.ValidationError(
                "You can only review services you were part of."
            )
        
        # Check if already reviewed
        if Review.objects.filter(service_request=value, reviewer=user).exists():
            raise serializers.ValidationError(
                "You have already reviewed this service."
            )
        
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        service_request = validated_data['service_request']
        
        # Determine review type and reviewee
        if user == service_request.customer:
            review_type = 'customer_to_mechanic'
            reviewee = service_request.mechanic
        else:
            review_type = 'mechanic_to_customer'
            reviewee = service_request.customer
        
        validated_data['reviewer'] = user
        validated_data['reviewee'] = reviewee
        validated_data['review_type'] = review_type
        validated_data['is_verified_purchase'] = True
        
        return super().create(validated_data)


# ============================================================================
# COMMUNICATION SERIALIZERS
# ============================================================================

class ChatMessageSerializer(serializers.ModelSerializer):
    """Serializer for real-time chat messages."""
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    sender_role = serializers.CharField(source='sender.role', read_only=True)
    
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'session', 'sender', 'sender_name', 'sender_role',
            'message', 'created_at'
        ]
        read_only_fields = ['id', 'session', 'sender', 'created_at']

    def create(self, validated_data):
        # Automatically set the sender to the current user
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


# ============================================================================
# PAYMENT SERIALIZERS
# ============================================================================

class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for transactions."""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display',
        read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'service_request', 'user', 'user_name', 'amount',
            'transaction_type', 'transaction_type_display', 'status',
            'status_display', 'description', 'reference_number',
            'payment_method', 'metadata', 'processed_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'reference_number', 'processed_at', 'created_at'
        ]


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for wallet."""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'user', 'user_name', 'balance', 'total_earned',
            'total_spent', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'balance', 'total_earned', 'total_spent',
            'created_at', 'updated_at'
        ]


class PromotionSerializer(serializers.ModelSerializer):
    """Serializer for promotions."""
    is_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Promotion
        fields = [
            'id', 'code', 'description', 'discount_type', 'discount_value',
            'max_discount', 'min_order_value', 'start_date', 'end_date',
            'usage_limit', 'usage_count', 'per_user_limit', 'applicable_to',
            'is_active', 'is_valid', 'created_at'
        ]
        read_only_fields = ['id', 'usage_count', 'created_at']


class ApplyPromotionSerializer(serializers.Serializer):
    """Serializer for applying promotion codes."""
    code = serializers.CharField(max_length=50, required=True)
    order_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True
    )


# ============================================================================
# VEHICLE SERIALIZERS
# ============================================================================

class VehicleSerializer(serializers.ModelSerializer):
    """Serializer for customer vehicles."""
    class Meta:
        model = Vehicle
        fields = [
            'id', 'make', 'model', 'year', 'license_plate',
            'vin', 'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_year(self, value):
        current_year = timezone.now().year
        if value < 1900 or value > current_year + 1:
            raise serializers.ValidationError(
                f"Year must be between 1900 and {current_year + 1}."
            )
        return value
    
    def create(self, validated_data):
        validated_data['customer'] = self.context['request'].user
        return super().create(validated_data)


# ============================================================================
# SERVICE TYPE SERIALIZERS
# ============================================================================

class ServiceTypeSerializer(serializers.ModelSerializer):
    """Serializer for service types."""
    class Meta:
        model = ServiceType
        fields = [
            'id', 'name', 'description', 'base_price',
            'estimated_duration', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# ============================================================================
# LOCATION SERIALIZERS
# ============================================================================

class LocationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for location updates."""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_role = serializers.CharField(source='user.role', read_only=True)
    
    class Meta:
        model = LocationUpdate
        fields = [
            'id', 'user', 'user_name', 'user_role', 'service_request',
            'latitude', 'longitude', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

# ============================================================================
# CAREER SERIALIZERS
# ============================================================================

class CareerSerializer(serializers.ModelSerializer):
    """Serializer for career applications."""
    class Meta:
        model = Career
        fields = ['id', 'name', 'email', 'phone', 'resume', 'cover_letter', 'applied_at']
        read_only_fields = ['id', 'applied_at']


# ============================================================================
# STATISTICS SERIALIZERS
# ============================================================================

class MechanicStatsSerializer(serializers.Serializer):
    """Serializer for mechanic statistics."""
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_services = serializers.IntegerField()
    completed_services = serializers.IntegerField()
    cancelled_services = serializers.IntegerField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    total_reviews = serializers.IntegerField()
    acceptance_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    this_month_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    this_month_services = serializers.IntegerField()


class CustomerStatsSerializer(serializers.Serializer):
    """Serializer for customer statistics."""
    total_requests = serializers.IntegerField()
    completed_requests = serializers.IntegerField()
    cancelled_requests = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_rating_given = serializers.DecimalField(max_digits=3, decimal_places=2)
    favorite_mechanics = MechanicSerializer(many=True)