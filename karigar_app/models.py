from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator, RegexValidator
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, UserManager
from django.db.models import Q, Avg, Count, F, Case, When, Value, DecimalField
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import uuid
from decimal import Decimal
from datetime import timedelta
import json


# ============================================================================
# CUSTOM MANAGERS AND QUERYSETS
# ============================================================================

class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that filters out soft-deleted objects by default."""
    
    def active(self):
        """Return only non-deleted objects."""
        return self.filter(deleted_at__isnull=True)
    
    def deleted(self):
        """Return only deleted objects."""
        return self.filter(deleted_at__isnull=False)
    
    def all_with_deleted(self):
        """Return all objects including deleted ones."""
        return self


class SoftDeleteManager(models.Manager):
    """Manager that filters out soft-deleted objects by default."""
    
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).active()
    
    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).all_with_deleted()
    
    def deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).deleted()


class CustomUserManager(UserManager):
    """Custom user manager for role-based user creation."""
    
    def create_customer(self, email, password=None, **extra_fields):
        """Create a customer user."""
        extra_fields.setdefault('role', 'customer')
        return self.create_user(email, password, **extra_fields)
    
    def create_mechanic(self, email, password=None, **extra_fields):
        """Create a mechanic user."""
        extra_fields.setdefault('role', 'mechanic')
        return self.create_user(email, password, **extra_fields)
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create a superuser."""
        extra_fields.setdefault('role', 'admin')
        return super().create_superuser(email, password, **extra_fields)
    
    def get_active_mechanics(self):
        """Get all available mechanics."""
        return self.filter(role='mechanic', is_active=True, mechanic_profile__is_available=True)
    
    def get_customers(self):
        """Get all customer users."""
        return self.filter(role='customer', is_active=True)


class MechanicQuerySet(SoftDeleteQuerySet):
    """Custom queryset for Mechanic model with advanced filtering."""
    
    def available(self):
        """Get available mechanics."""
        return self.active().filter(is_available=True, user__is_active=True)
    
    def nearby(self, latitude, longitude, radius_km=15):
        """Get mechanics within radius using simple distance calculation."""
        # For production, use GeoDjango with PostGIS for better performance
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in km
        lat1, lon1 = radians(latitude), radians(longitude)
        
        mechanics = self.available().filter(
            current_latitude__isnull=False,
            current_longitude__isnull=False
        )
        
        nearby_mechanics = []
        for mechanic in mechanics:
            if mechanic.current_latitude and mechanic.current_longitude:
                lat2, lon2 = radians(mechanic.current_latitude), radians(mechanic.current_longitude)
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                distance = R * c
                
                if distance <= radius_km:
                    nearby_mechanics.append((mechanic, distance))
        
        return sorted(nearby_mechanics, key=lambda x: x[1])
    
    def top_rated(self, limit=10):
        """Get top-rated mechanics."""
        return self.available().order_by('-average_rating')[:limit]
    
    def with_stats(self):
        """Annotate with statistics."""
        return self.annotate(
            completed_count=Count('user__service_requests_as_mechanic', 
                                 filter=Q(user__service_requests_as_mechanic__status='completed')),
            avg_rating=Avg('average_rating'),
            response_rate=Case(
                When(total_services_completed__gt=0, 
                     then=F('total_services_completed') * 100 / F('total_services_completed')),
                default=Value(0),
                output_field=DecimalField()
            )
        )
    
    def by_specialization(self, specialization):
        """Get mechanics with specific specialization."""
        return self.available().filter(specializations__contains=specialization)


class MechanicManager(SoftDeleteManager):
    """Manager for Mechanic model."""
    
    def get_queryset(self):
        return MechanicQuerySet(self.model, using=self._db).active()
    
    def available(self):
        return self.get_queryset().available()
    
    def nearby(self, latitude, longitude, radius_km=15):
        return self.get_queryset().nearby(latitude, longitude, radius_km)
    
    def top_rated(self, limit=10):
        return self.get_queryset().top_rated(limit)
    
    def with_stats(self):
        return self.get_queryset().with_stats()


class ServiceRequestQuerySet(SoftDeleteQuerySet):
    """Custom queryset for ServiceRequest model."""
    
    def pending(self):
        """Get pending requests."""
        return self.active().filter(status='pending')
    
    def active_requests(self):
        """Get active requests (accepted or in progress)."""
        return self.active().filter(status__in=['accepted', 'in_progress'])
    
    def completed(self):
        """Get completed requests."""
        return self.active().filter(status='completed')
    
    def by_customer(self, customer):
        """Get requests for a specific customer."""
        return self.active().filter(customer=customer)
    
    def by_mechanic(self, mechanic):
        """Get requests for a specific mechanic."""
        return self.active().filter(mechanic=mechanic)
    
    def high_priority(self):
        """Get high-priority requests (old pending requests)."""
        cutoff_time = timezone.now() - timedelta(minutes=30)
        return self.pending().filter(created_at__lt=cutoff_time)
    
    def with_stats(self):
        """Annotate with statistics."""
        return self.annotate(
            duration_minutes=Case(
                When(completion_time__isnull=False, actual_arrival_time__isnull=False,
                     then=(F('completion_time') - F('actual_arrival_time'))),
                default=Value(None)
            )
        )


class ServiceRequestManager(SoftDeleteManager):
    """Manager for ServiceRequest model."""
    
    def get_queryset(self):
        return ServiceRequestQuerySet(self.model, using=self._db).active()
    
    def pending(self):
        return self.get_queryset().pending()
    
    def active_requests(self):
        return self.get_queryset().active_requests()
    
    def completed(self):
        return self.get_queryset().completed()
    
    def by_customer(self, customer):
        return self.get_queryset().by_customer(customer)
    
    def by_mechanic(self, mechanic):
        return self.get_queryset().by_mechanic(mechanic)

    def delete_expired_pending_requests(self, timeout_seconds=30):
        """
        Finds and soft-deletes pending ServiceRequests older than timeout_seconds.
        """
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(seconds=timeout_seconds)
        
        expired_requests = self.get_queryset().filter(
            status='pending',
            created_at__lt=cutoff_time
        )
        
        count = expired_requests.count()
        
        # Perform soft delete on the queryset
        for req in expired_requests:
            req.soft_delete()
            
        return count


# ============================================================================
# ABSTRACT BASE MODELS
# ============================================================================

class BaseModel(models.Model):
    """Abstract base model with common fields."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class SoftDeleteModel(BaseModel):
    """Abstract base model with soft delete functionality."""
    
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    objects = SoftDeleteManager()
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def soft_delete(self):
        """Soft delete this object."""
        self.deleted_at = timezone.now()
        self.save()
    
    def restore(self):
        """Restore soft-deleted object."""
        self.deleted_at = None
        self.save()
    
    def is_deleted(self):
        """Check if object is soft-deleted."""
        return self.deleted_at is not None


class AuditModel(SoftDeleteModel):
    """Abstract base model with audit logging."""
    
    created_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created_by'
    )
    updated_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated_by'
    )
    
    class Meta:
        abstract = True


# ============================================================================
# USER AND AUTHENTICATION MODELS
# ============================================================================

class User(AbstractUser):
    """
    Extended User model with role-based access control and advanced features.
    
    Roles:
    - 'customer': Regular user requesting mechanic services
    - 'mechanic': Service provider offering mechanic services
    - 'admin': Administrator with full access
    """
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('mechanic', 'Mechanic'),
        ('admin', 'Administrator'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer',
        db_index=True
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Invalid phone number')]
    )
    profile_picture = models.ImageField(
        upload_to='profile_pictures/%Y/%m/',
        blank=True,
        null=True
    )
    is_verified = models.BooleanField(default=False, db_index=True)
    verification_token = models.CharField(max_length=255, blank=True, null=True)
    verification_token_expires = models.DateTimeField(blank=True, null=True)
    
    # Account status
    is_suspended = models.BooleanField(default=False)
    suspension_reason = models.TextField(blank=True)
    suspension_date = models.DateTimeField(blank=True, null=True)
    
    # Profile completion
    profile_completion_percentage = models.PositiveIntegerField(default=0)
    
    # Preferences
    preferred_language = models.CharField(
        max_length=10,
        default='en',
        choices=[('en', 'English'), ('es', 'Spanish'), ('fr', 'French')]
    )
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Statistics
    total_requests = models.PositiveIntegerField(default=0)
    total_completed = models.PositiveIntegerField(default=0)
    total_cancelled = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    
    objects = CustomUserManager()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role', 'is_active']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['is_suspended']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
    
    def is_mechanic(self):
        return self.role == 'mechanic'
    
    def is_customer(self):
        return self.role == 'customer'
    
    def is_admin(self):
        return self.role == 'admin' or self.is_superuser
    
    def can_request_service(self):
        """Check if user can request service."""
        return self.is_active and not self.is_suspended 
    
    def can_accept_service(self):
        """Check if user can accept service requests."""
        return self.is_mechanic() and self.is_active and not self.is_suspended and self.is_verified
    
    def suspend(self, reason=''):
        """Suspend user account."""
        self.is_suspended = True
        self.suspension_reason = reason
        self.suspension_date = timezone.now()
        self.save()
    
    def unsuspend(self):
        """Unsuspend user account."""
        self.is_suspended = False
        self.suspension_reason = ''
        self.suspension_date = None
        self.save()
    
    def get_profile_completion(self):
        """Calculate profile completion percentage."""
        fields = ['first_name', 'last_name', 'email', 'phone']
        completed = sum(1 for field in fields if getattr(self, field))
        
        if self.is_mechanic() and hasattr(self, 'mechanic_profile'):
            mechanic = self.mechanic_profile
            mechanic_fields = [ 'specializations', 'years_of_experience']
            completed += sum(1 for field in mechanic_fields if getattr(mechanic, field))
            fields.extend(mechanic_fields)
        
        self.profile_completion_percentage = int((completed / len(fields)) * 100)
        self.save()
        return self.profile_completion_percentage


class DeviceToken(BaseModel):
    """Store device tokens for push notifications."""
    
    DEVICE_TYPE_CHOICES = (
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.TextField(unique=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES)
    device_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'token')
        indexes = [models.Index(fields=['user', 'is_active'])]
    
    def __str__(self):
        return f"{self.user.email} - {self.device_type}"


# ============================================================================
# MECHANIC MODELS
# ============================================================================
class MechanicDocument(BaseModel):
    """Store documents for mechanics."""
    
    mechanic = models.ForeignKey('Mechanic',on_delete=models.CASCADE,    related_name='documents'
    )
    document_type = models.CharField(max_length=100)
    document_file = models.FileField(upload_to='mechanic_documents/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.mechanic.user.get_full_name()} - {self.document_type}"
class Mechanic(SoftDeleteModel):
    """
    Mechanic profile model with advanced features.
    
    Tracks specializations, ratings, availability, location, and performance metrics.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='mechanic_profile'
    )
    specializations = models.JSONField(
        default=list,
        help_text='List of service specializations',blank=True, null=True
    )
    years_of_experience = models.PositiveIntegerField(default=0)
    bio = models.TextField(blank=True, help_text='Professional biography')
    
    # Rating and reviews
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    total_reviews = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)
    
    # Availability and location
    is_available = models.BooleanField(default=True, db_index=True)
    current_latitude = models.FloatField(blank=True, null=True)
    current_longitude = models.FloatField(blank=True, null=True)
    last_location_update = models.DateTimeField(blank=True, null=True)
    
    # Service area
    service_radius_km = models.PositiveIntegerField(default=15)
    
    # Performance metrics
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_services_completed = models.PositiveIntegerField(default=0)
    total_services_cancelled = models.PositiveIntegerField(default=0)
    average_service_duration = models.PositiveIntegerField(default=0, help_text='In minutes')
    acceptance_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    #documents
    identity_document = models.ManyToManyField('MechanicDocument', related_name='identity_documents', blank=True)


    
    # Account status
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(blank=True, null=True)
    
    objects = MechanicManager()
    
    class Meta:
        ordering = ['-average_rating', '-total_services_completed']
        indexes = [
            models.Index(fields=['is_available']),
            models.Index(fields=['average_rating']),
            models.Index(fields=['current_latitude', 'current_longitude']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - Mechanic"
    
     
    def update_rating(self):
        """Recalculate average rating from all reviews."""
        from django.db.models import Avg
        reviews = Review.objects.filter(
            reviewee=self.user,
            review_type='customer_to_mechanic'
        )
        if reviews.exists():
            stats = reviews.aggregate(
                avg_rating=Avg('rating'),
                count=Count('id')
            )
            self.average_rating = stats['avg_rating'] or 0
            self.total_reviews = stats['count']
            self.save()
    
    def update_performance_metrics(self):
        """Update performance metrics based on completed services."""
        from django.db.models import Avg, Count
        
        completed = ServiceRequest.objects.filter(
            mechanic=self.user,
            status='completed'
        )
        
        if completed.exists():
            stats = completed.aggregate(
                total_earnings=models.Sum('actual_cost'),
                avg_duration=Avg(
                    models.F('completion_time') - models.F('actual_arrival_time'),
                    output_field=models.DurationField()
                ),
                count=Count('id')
            )
            
            self.total_services_completed = stats['count']
            self.total_earnings = stats['total_earnings'] or 0
            
            if stats['avg_duration']:
                self.average_service_duration = int(stats['avg_duration'].total_seconds() / 60)
            
            self.save()
    
    def get_distance_from(self, latitude, longitude):
        """Calculate distance from given coordinates."""
        if not self.current_latitude or not self.current_longitude:
            return None
        
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371
        lat1, lon1 = radians(self.current_latitude), radians(self.current_longitude)
        lat2, lon2 = radians(latitude), radians(longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    def is_within_service_area(self, latitude, longitude):
        """Check if location is within service area."""
        distance = self.get_distance_from(latitude, longitude)
        return distance is not None and distance <= self.service_radius_km


# ============================================================================
# SERVICE REQUEST MODELS
# ============================================================================

class ServiceRequest(SoftDeleteModel):
    """
    Service request model with advanced lifecycle management.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('emergency', 'Emergency'),
    )
    
    # Basic info
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='service_requests_as_customer'
    )
    mechanic = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_requests_as_mechanic'
    )
    service_type = models.CharField(max_length=100)
    description = models.TextField()
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='normal'
    )
    
    # Location
    customer_latitude = models.FloatField()
    customer_longitude = models.FloatField()
    service_address = models.TextField(blank=True)
    
    # Status and timeline
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    estimated_arrival_time = models.PositiveIntegerField(blank=True, null=True)
    actual_arrival_time = models.DateTimeField(blank=True, null=True)
    start_time = models.DateTimeField(blank=True, null=True)
    completion_time = models.DateTimeField(blank=True, null=True)
    
    # Pricing
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )
    actual_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )
    
    # Additional info
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.CharField(
        max_length=20,
        choices=[('customer', 'Customer'), ('mechanic', 'Mechanic'), ('admin', 'Admin')],
        blank=True
    )
    
    objects = ServiceRequestManager()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['mechanic', 'status']),
            models.Index(fields=['priority']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Service Request #{self.id} - {self.service_type}"
    
    def get_duration(self):
        """Calculate service duration in minutes."""
        if self.actual_arrival_time and self.completion_time:
            duration = self.completion_time - self.actual_arrival_time
            return int(duration.total_seconds() / 60)
        return None
    
    def calculate_final_amount(self):
        """Calculate final amount after discount and tax."""
        if self.actual_cost:
            subtotal = self.actual_cost - self.discount_amount
            self.final_amount = subtotal + self.tax_amount
            self.save()
    
    def accept(self, mechanic, estimated_arrival_minutes):
        """Accept service request."""
        if self.status != 'pending':
            raise ValidationError('Request is not pending')
        
        self.mechanic = mechanic
        self.status = 'accepted'
        self.estimated_arrival_time = estimated_arrival_minutes
        self.actual_arrival_time = timezone.now()
        self.save()
    
    def start_service(self):
        """Start service."""
        if self.status != 'accepted':
            raise ValidationError('Request must be accepted first')
        
        self.status = 'in_progress'
        self.start_time = timezone.now()
        self.save()
    
    def complete_service(self, actual_cost=None):
        """Complete service."""
        if self.status != 'in_progress':
            raise ValidationError('Service must be in progress')
        
        self.status = 'completed'
        self.completion_time = timezone.now()
        if actual_cost:
            self.actual_cost = actual_cost
        self.calculate_final_amount()
        self.save()
    
    def cancel(self, reason='', cancelled_by='customer'):
        """Cancel service request."""
        if self.status in ['completed', 'cancelled']:
            raise ValidationError('Cannot cancel completed or already cancelled request')
        
        self.status = 'cancelled'
        self.cancellation_reason = reason
        self.cancelled_by = cancelled_by
        self.save()


class ServiceRequestAttachment(BaseModel):
    """Store attachments for service requests."""
    
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='service_requests/%Y/%m/')
    file_type = models.CharField(max_length=50)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Attachment for {self.service_request.id}"


# ============================================================================
# LOCATION AND TRACKING MODELS
# ============================================================================

class LocationUpdate(BaseModel):
    """
    Stores real-time location updates for a user during an active ServiceRequest.
    This is primarily for tracking purposes, similar to inDrive.
    """
    service_request = models.ForeignKey(
        'ServiceRequest',
        on_delete=models.CASCADE,
        related_name='location_updates',
        help_text='The service request this location update is for.'
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='location_updates'
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    class Meta:
        verbose_name = 'Location Update'
        verbose_name_plural = 'Location Updates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['service_request']),
            models.Index(fields=['user']),
        ]
        
    def __str__(self):
        return f"Location for {self.user.email} at {self.latitude}, {self.longitude}"

# ============================================================================
# REVIEW AND RATING MODELS
# ============================================================================

class Review(SoftDeleteModel):
    """Bidirectional review and rating system."""
    
    REVIEW_TYPE_CHOICES = (
        ('customer_to_mechanic', 'Customer Review of Mechanic'),
        ('mechanic_to_customer', 'Mechanic Review of Customer'),
    )
    
    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='review'
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reviews_given'
    )
    reviewee = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reviews_received'
    )
    review_type = models.CharField(max_length=30, choices=REVIEW_TYPE_CHOICES)
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    # Detailed ratings
    quality_rating = models.PositiveIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Quality of work'
    )
    punctuality_rating = models.PositiveIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Punctuality'
    )
    communication_rating = models.PositiveIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Communication'
    )
    
    comment = models.TextField(blank=True)
    is_anonymous = models.BooleanField(default=False)
    is_verified_purchase = models.BooleanField(default=True)
    helpful_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ('service_request', 'reviewer')
        indexes = [
            models.Index(fields=['reviewee', 'review_type']),
            models.Index(fields=['rating']),
        ]
    
    def __str__(self):
        return f"Review: {self.reviewer.get_full_name()} → {self.reviewee.get_full_name()} ({self.rating}★)"


class ReviewResponse(BaseModel):
    """Response to reviews."""
    
    review = models.OneToOneField(
        Review,
        on_delete=models.CASCADE,
        related_name='response'
    )
    responder = models.ForeignKey(User, on_delete=models.CASCADE)
    response_text = models.TextField()
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Response to review #{self.review.id}"


# ============================================================================
# COMMUNICATION MODELS
# ============================================================================
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator, RegexValidator
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, UserManager
from django.db.models import Q, Avg, Count, F, Case, When, Value, DecimalField
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import uuid
from decimal import Decimal
from datetime import timedelta
import json


# ============================================================================
# CUSTOM MANAGERS AND QUERYSETS
# ============================================================================

class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that filters out soft-deleted objects by default."""
    
    def active(self):
        """Return only non-deleted objects."""
        return self.filter(deleted_at__isnull=True)
    
    def deleted(self):
        """Return only deleted objects."""
        return self.filter(deleted_at__isnull=False)
    
    def all_with_deleted(self):
        """Return all objects including deleted ones."""
        return self

# ... (rest of the existing models.py content) ...

# ============================================================================
# REAL-TIME CHAT AND TRACKING MODELS (NEW)
# ============================================================================

class ChatSession(BaseModel):
    """
    Represents a real-time chat session linked to a ServiceRequest.
    The chat is ephemeral (no history stored long-term).
    """
    service_request = models.OneToOneField(
        'ServiceRequest',
        on_delete=models.CASCADE,
        related_name='chat_session',
        help_text='The service request this chat session is for.'
    )
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        verbose_name = 'Chat Session'
        verbose_name_plural = 'Chat Sessions'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Chat for SR: {self.service_request.id}"

class ChatMessage(BaseModel):
    """
    Represents a single message in a ChatSession.
    Note: Per user request, this model is for real-time transmission only.
    For a no-history requirement, these messages would typically be deleted
    shortly after transmission or not persisted at all. We include the model
    for potential future logging/debugging, but the application logic will
    treat it as ephemeral.
    """
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    message = models.TextField()
    
    class Meta:
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
        ordering = ['created_at']
        
    def __str__(self):
        return f"Message from {self.sender.email} in session {self.session.id}"

 


# ============================================================================
# PAYMENT AND TRANSACTION MODELS
# ============================================================================

class Transaction(SoftDeleteModel):
    """Financial transaction tracking."""
    
    TRANSACTION_TYPE_CHOICES = (
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('withdrawal', 'Withdrawal'),
        ('bonus', 'Bonus'),
        ('penalty', 'Penalty'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )
    
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    description = models.TextField(blank=True)
    reference_number = models.CharField(max_length=255, unique=True)
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ('credit_card', 'Credit Card'),
            ('debit_card', 'Debit Card'),
            ('wallet', 'Wallet'),
            ('bank_transfer', 'Bank Transfer'),
        ]
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['reference_number']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()}: ${self.amount} - {self.user.email}"


class Wallet(BaseModel):
    """User wallet for storing balance."""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        indexes = [models.Index(fields=['user'])]
    
    def __str__(self):
        return f"Wallet: {self.user.email} - Balance: ${self.balance}"
    
    def add_balance(self, amount, description=''):
        """Add balance to wallet."""
        self.balance += amount
        self.total_earned += amount
        self.save()
        
        Transaction.objects.create(
            user=self.user,
            amount=amount,
            transaction_type='bonus',
            status='completed',
            description=description,
            reference_number=f"WALLET_{self.user.id}_{timezone.now().timestamp()}",
            payment_method='wallet'
        )
    
    def deduct_balance(self, amount, description=''):
        """Deduct balance from wallet."""
        if self.balance < amount:
            raise ValidationError('Insufficient balance')
        
        self.balance -= amount
        self.total_spent += amount
        self.save()
        
        Transaction.objects.create(
            user=self.user,
            amount=amount,
            transaction_type='payment',
            status='completed',
            description=description,
            reference_number=f"WALLET_{self.user.id}_{timezone.now().timestamp()}",
            payment_method='wallet'
        )


# ============================================================================
# PROMOTION AND DISCOUNT MODELS
# ============================================================================

class Promotion(SoftDeleteModel):
    """Promotional codes and discounts."""
    
    TYPE_CHOICES = (
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount'),
        ('free_service', 'Free Service'),
    )
    
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    discount_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    max_discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text='Maximum discount amount'
    )
    min_order_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    # Validity
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(blank=True, null=True)
    usage_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(default=1)
    
    # Restrictions
    applicable_to = models.CharField(
        max_length=50,
        choices=[
            ('all', 'All Users'),
            ('new_users', 'New Users Only'),
            ('mechanics', 'Mechanics Only'),
        ],
        default='all'
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Promotion: {self.code}"
    
    def is_valid(self):
        """Check if promotion is valid."""
        now = timezone.now()
        return (
            self.is_active and
            self.start_date <= now <= self.end_date and
            (self.usage_limit is None or self.usage_count < self.usage_limit)
        )
    
    def calculate_discount(self, amount):
        """Calculate discount amount."""
        if not self.is_valid():
            return 0
        
        if self.discount_type == 'percentage':
            discount = amount * (self.discount_value / 100)
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = self.discount_value
        
        return min(discount, amount)


# ============================================================================
# SETTINGS AND PREFERENCES MODELS
# ============================================================================

class UserPreference(BaseModel):
    """User preferences and settings."""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='preferences'
    )
    
    # Notifications
    notifications_enabled = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Privacy
    location_sharing_enabled = models.BooleanField(default=True)
    profile_visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('mechanics_only', 'Mechanics Only'),
        ],
        default='public'
    )
    
    # Preferences
    preferred_payment_method = models.CharField(
        max_length=50,
        choices=[
            ('credit_card', 'Credit Card'),
            ('debit_card', 'Debit Card'),
            ('wallet', 'Wallet'),
            ('cash', 'Cash'),
        ],
        blank=True
    )
    emergency_contact = models.CharField(max_length=20, blank=True)
    preferred_language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    theme = models.CharField(
        max_length=20,
        choices=[('light', 'Light'), ('dark', 'Dark')],
        default='light'
    )
    
    # Service preferences
    preferred_service_types = models.JSONField(default=list)
    max_service_radius = models.PositiveIntegerField(default=15)
    
    class Meta:
        verbose_name_plural = "User Preferences"
    
    def __str__(self):
        return f"Preferences for {self.user.email}"


# ============================================================================
# SIGNAL HANDLERS
# ============================================================================

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create related objects when user is created."""
    if created:
        UserPreference.objects.get_or_create(user=instance)
        Wallet.objects.get_or_create(user=instance)
        if instance.device_tokens.count() == 0:
            pass  # Device tokens are created on app login


@receiver(post_save, sender=Review)
def update_mechanic_rating(sender, instance, created, **kwargs):
    """Update mechanic rating when review is posted."""
    if instance.review_type == 'customer_to_mechanic':
        try:
            mechanic = instance.reviewee.mechanic_profile
            mechanic.update_rating()
        except Mechanic.DoesNotExist:
            pass


@receiver(post_save, sender=ServiceRequest)
def update_user_statistics(sender, instance, created, **kwargs):
    """Update user statistics when service request changes."""
    if created:
        instance.customer.total_requests += 1
        instance.customer.save()
    
    if instance.status == 'completed':
        instance.customer.total_completed += 1
        instance.customer.save()
        
        if instance.mechanic:
            instance.mechanic.total_completed += 1
            instance.mechanic.save()
    
    elif instance.status == 'cancelled':
        instance.customer.total_cancelled += 1
        instance.customer.save()


@receiver(post_save, sender=ChatMessage)
def notify_message_recipient(sender, instance, created, **kwargs):
    """Send notification when new message is received."""
    if created:
        # TODO: Implement push notification logic
        pass
class Career (models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    resume = models.FileField(upload_to='resumes/%Y/%m/')
    cover_letter = models.TextField(blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"
 
# ============================================================================
# VEHICLE MANAGEMENT MODELS
# ============================================================================

class Vehicle(SoftDeleteModel):
    """
    Model to store customer vehicle information.
    """
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vehicles',
        limit_choices_to={'role': 'customer'}
    )
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.PositiveSmallIntegerField()
    license_plate = models.CharField(max_length=20, unique=True)
    vin = models.CharField(
        max_length=17,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[A-HJ-NPR-Z0-9]{17}$',
                message='VIN must be 17 characters and exclude I, O, Q.'
            )
        ]
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Customer Vehicle"
        verbose_name_plural = "Customer Vehicles"
        unique_together = ('customer', 'license_plate')

    def __str__(self):
        return f"{self.make} {self.model} ({self.license_plate})"


# ============================================================================
# SERVICE AND PRICING MODELS
# ============================================================================

class ServiceType(SoftDeleteModel):
    """
    Canonical list of services offered by the platform.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_duration = models.PositiveIntegerField(help_text='Duration in minutes')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Service Type"
        verbose_name_plural = "Service Types"

    def __str__(self):
        return self.name


class MechanicService(SoftDeleteModel):
    """
    Links a Mechanic to a ServiceType, allowing for custom pricing and availability.
    """
    mechanic = models.ForeignKey(
        'Mechanic', # Assuming Mechanic is a separate model or profile linked to User
        on_delete=models.CASCADE,
        related_name='offered_services'
    )
    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.CASCADE,
        related_name='mechanic_offerings'
    )
    custom_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Overrides ServiceType base_price if set.'
    )
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ('mechanic', 'service_type')
        verbose_name = "Mechanic Service Offering"
        verbose_name_plural = "Mechanic Service Offerings"

    def __str__(self):
        price = self.custom_price if self.custom_price else self.service_type.base_price
        return f"{self.mechanic.user.get_full_name()} offers {self.service_type.name} for ${price}"


# ============================================================================
# SERVICE REQUEST DETAIL MODELS
# ============================================================================

class ServiceRequestItem(SoftDeleteModel):
    """
    Detailed line items for a ServiceRequest (parts and labor).
    """
    ITEM_TYPE_CHOICES = (
        ('labor', 'Labor'),
        ('part', 'Part'),
        ('fee', 'Fee'),
    )

    service_request = models.ForeignKey(
        'ServiceRequest', # Assuming ServiceRequest is a separate model
        on_delete=models.CASCADE,
        related_name='items'
    )
    description = models.CharField(max_length=255)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_completed = models.BooleanField(default=False)
    item_type = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES, default='labor')

    class Meta:
        verbose_name = "Service Request Item"
        verbose_name_plural = "Service Request Items"

    def __str__(self):
        return f"{self.description} x {self.quantity} for Request {self.service_request.id}"

    @property
    def total_price(self):
        return self.quantity * self.unit_price

# In emechanics/models.py (or a new webhooks.py file)

class Webhook(BaseModel):
    """Stores configuration for external webhooks."""
    
    # The UUID is already provided by the BaseModel's 'id' field
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    EVENT_CHOICES = (
        ('payment_success', 'Payment Success Notification'),
        ('mechanic_status', 'Mechanic Status Change'),
        # Add other events as needed
    )
    
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    target_url = models.URLField(max_length=500, help_text="The external URL to send the payload to.")
    is_active = models.BooleanField(default=True)
    secret_key = models.CharField(max_length=128, blank=True, null=True, 
                                  help_text="Secret key for signing/verifying payloads.")
    
    # Optional: Link to a user or service
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='webhooks')
    
    def __str__(self):
        return f"{self.event_type} Webhook for {self.user.email}"
