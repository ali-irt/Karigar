# models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid
 
 
class User(AbstractUser):
    """
    Custom user model for both customers and mechanics.
    """
    USER_TYPES = [
        ('customer', 'Customer'),
        ('mechanic', 'Mechanic'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='customer')
    is_verified = models.BooleanField(default=False)
    is_mechanic = models.BooleanField(default=False)
    profile_image = models.ImageField(upload_to='profiles/', null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Make username optional
    username = models.CharField(max_length=150, blank=True, null=True)
    
    # Use email as the login field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone']
    
    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['user_type']),
        ]
    
    def __str__(self):
        return self.email
    
    def save(self, *args, **kwargs):
        # Auto-set is_mechanic based on user_type
        self.is_mechanic = (self.user_type == 'mechanic')
        super().save(*args, **kwargs)


class CustomerProfile(models.Model):
    """
    Extended profile for customers.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    default_payment_method_id = models.CharField(max_length=128, blank=True, null=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Customer Profile - {self.user.email}"


class MechanicProfile(models.Model):
    """
    Extended profile for mechanics.
    """
    APPROVAL_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    AVAILABILITY_STATUS = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('busy', 'Busy'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mechanic_profile')
    bio = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    
    # Ratings & Stats
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    rating_count = models.IntegerField(default=0)
    total_jobs_completed = models.PositiveIntegerField(default=0)
    
    # Availability
    availability_status = models.CharField(max_length=20, choices=AVAILABILITY_STATUS, default='offline')
    is_available = models.BooleanField(default=False)
    
    # Pricing
    hourly_base = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)
    
    # Admin approval
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='pending')
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_mechanics'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Profile visibility
    is_published = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['is_available']),
            models.Index(fields=['rating']),
            models.Index(fields=['approval_status']),
            models.Index(fields=['city']),
        ]
    
    def __str__(self):
        return f"Mechanic Profile - {self.user.email}"


class MechanicDocument(models.Model):
    """
    Documents uploaded by mechanics for verification.
    """
    DOCUMENT_TYPES = [
        ('id_card', 'ID Card'),
        ('license', 'License'),
        ('certificate', 'Certificate'),
        ('insurance', 'Insurance'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mechanic = models.ForeignKey(
        MechanicProfile, 
        on_delete=models.CASCADE, 
        related_name='documents'
    )
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    document_file = models.FileField(upload_to='mechanic_docs/')
    document_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['mechanic', 'status']),
            models.Index(fields=['document_type']),
        ]
    
    def __str__(self):
        return f"{self.document_type} - {self.mechanic.user.email}"


class OTP(models.Model):
    """
    OTP verification for phone numbers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20)
    otp_code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        indexes = [
            models.Index(fields=['phone', 'otp_code']),
        ]
    
    def is_valid(self):
        """Check if OTP is still valid."""
        return not self.is_verified and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"OTP for {self.phone}"

# ---------- Location model (Geo) ----------
class Location(models.Model):
    """
    Generic location. Use PostGIS PointField for precise geolocation and fast proximity queries.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # If you don't use PostGIS, replace with latitude/longitude floats.
    address = models.CharField(max_length=512, blank=True)
    name = models.CharField(max_length=200, blank=True)  # 'Downtown, Lahore' / 'User location'
    created_at = models.DateTimeField(auto_now_add=True)


# ---------- Vehicles ----------
class Vehicle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vehicles')
    make = models.CharField(max_length=100)  # e.g., Honda
    model = models.CharField(max_length=100) # e.g., Civic
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    plate_number = models.CharField(max_length=64, blank=True, null=True)
    vin = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['owner']), models.Index(fields=['plate_number'])]

# ---------- Service catalogue ----------
class ServiceType(models.Model):
    """
    Canonical list of services (oil change, battery replacement, towing).
    """
    slug = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    base_duration_minutes = models.PositiveIntegerField(default=60)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['slug']), models.Index(fields=['title'])]

class MechanicService(models.Model):
    """
    Which services a mechanic can provide, with optional custom pricing.
    """
    mechanic = models.ForeignKey(MechanicProfile, on_delete=models.CASCADE, related_name='services')
    service_type = models.ForeignKey(ServiceType, on_delete=models.CASCADE)
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    custom_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('mechanic', 'service_type')
        indexes = [models.Index(fields=['mechanic']), models.Index(fields=['service_type'])]

# ---------- Job / Request lifecycle ----------
class JobRequest(models.Model):
    """
    A customer creates a request for a service. This is the core.
    """
    STATUS_CHOICES = [
        ('open', 'Open'),                 # created, searching/quoting
        ('quoted', 'Quoted'),             # one or more quotes given
        ('assigned', 'Assigned'),         # mechanic assigned / on the way
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='job_requests')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True)
    service_type = models.ForeignKey(ServiceType, on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True)
    pickup_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, related_name='pickup_jobs')
    preferred_time = models.DateTimeField(null=True, blank=True)  # immediate vs scheduled
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # cached best quote / final price
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['customer']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

class Quote(models.Model):
    """
    Mechanic or system provides a quote for a JobRequest.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(JobRequest, on_delete=models.CASCADE, related_name='quotes')
    mechanic = models.ForeignKey(MechanicProfile, on_delete=models.CASCADE, related_name='quotes')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_duration_minutes = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('job', 'mechanic')
        indexes = [models.Index(fields=['mechanic']), models.Index(fields=['job', 'accepted'])]

class JobAssignment(models.Model):
    """
    Tracks assignment and the mechanic's lifecycle during a job.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(JobRequest, on_delete=models.CASCADE, related_name='assignment')
    mechanic = models.ForeignKey(MechanicProfile, on_delete=models.CASCADE, related_name='assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, default='assigned')  # similar to job status but per-assignment

  
# ---------- Payments & Transactions ----------
class Payment(models.Model):
    PAYMENT_METHOD = [
        ('card', 'Card'),
        ('wallet', 'Wallet'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(JobRequest, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    mechanic_payout = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    method = models.CharField(max_length=32, choices=PAYMENT_METHOD)
    status = models.CharField(max_length=32, choices=PAYMENT_STATUS, default='pending')
    processor_transaction_id = models.CharField(max_length=256, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status']), models.Index(fields=['method'])]

class Transaction(models.Model):
    """
    Ledger of money movement for accounting.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    from_account = models.CharField(max_length=128)  # e.g., 'customer_card_xxx'
    to_account = models.CharField(max_length=128)    # e.g., 'mechanic_wallet_yyy'
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=['created_at'])]

# ---------- Ratings & Reviews ----------
class Rating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(JobRequest, on_delete=models.CASCADE, related_name='rating')
    mechanic = models.ForeignKey(MechanicProfile, on_delete=models.CASCADE, related_name='ratings')
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()  # 1-5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['mechanic']), models.Index(fields=['score'])]

# ---------- Availability, schedule & real-time pings ----------
class AvailabilitySlot(models.Model):
    mechanic = models.ForeignKey(MechanicProfile, on_delete=models.CASCADE, related_name='availability')
    weekday = models.PositiveSmallIntegerField()  # 0 = Monday ... 6 = Sunday
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('mechanic', 'weekday', 'start_time', 'end_time')

class MechanicLocationPing(models.Model):
    mechanic = models.ForeignKey(MechanicProfile, on_delete=models.CASCADE, related_name='location_pings')
    ping_time = models.DateTimeField(default=timezone.now)
    heading = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)


# ---------- Notifications & misc ----------
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.TextField()
    read = models.BooleanField(default=False)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'read'])]

# Promo / Coupons
class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    discount_flat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Career(models.Model):
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    responsibilities = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    posted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
