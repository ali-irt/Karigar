# emechanics/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Sum
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.shortcuts import redirect, render
from django.contrib.auth.models import User
from .models import *
from django.db.models import Q
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .serializers import *
from .permissions import *
from rest_framework_simplejwt.tokens import RefreshToken

#--------------------------------------------
#website views
#--------------------------------------------
from .models import *
def index(request):
    return render(request, 'karigar_app/index.html')

def about(request):       
    return render(request, 'karigar_app/about.html')

def services(request):
    return render(request, 'karigar_app/services.html')

def how_it_work(request):
    return render(request, 'karigar_app/how-it-work.html')

def safety(request):
    return render(request, 'karigar_app/safety.html')

def faq(request):
    return render(request, 'karigar_app/faq.html')

 

def career(request):
    jobs = Career.objects.filter(is_active=True).order_by('-posted_at')
    return render(request, 'karigar_app/career.html', {'jobs': jobs})



def contact(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        subject = request.POST.get("subject")
        message = request.POST.get("message")

        # Basic validation
        if not name or not email or not subject or not message:
            messages.error(request, "Please fill all fields.")
            return redirect("contact")

        # OPTIONAL: Save to DB or email
        # ContactMessage.objects.create(name=name, email=email, subject=subject, message=message)

        messages.success(request, "Your message has been sent successfully! Our team will contact you soon.")
        return redirect("contact")

    return render(request, 'karigar_app/contact.html')
def login_view(request):
    if request.method == "POST":
        email_or_username = request.POST.get("username")
        password = request.POST.get("password")

        # If user enters username, convert to email
        if '@' in email_or_username:
            email = email_or_username
        else:
            try:
                email = User.objects.get(username=email_or_username).email
            except User.DoesNotExist:
                messages.error(request, "Invalid login credentials!")
                return redirect("login_view")

        user = authenticate(request, email=email, password=password)

        if user:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username or user.email}!")

            # Redirect to next if available
            next_url = request.GET.get("next")
            if next_url:
                return redirect(next_url)

            # Mechanic redirect
            if user.user_type == "mechanic" or user.is_mechanic:
                return redirect("mechanic_dashboard")

            # Customer redirect
            return redirect("index")

        else:
            messages.error(request, "Invalid credentials!")
            return redirect("login_view")

    return render(request, "karigar_app/login.html")
 

def mechanic_register(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")

        cnic_front = request.FILES.get("cnicFront")
        cnic_back = request.FILES.get("cnicBack")

        # VALIDATIONS
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists!")
            return redirect("mechanic_register")

        if User.objects.filter(phone=phone).exists():
            messages.error(request, "Phone already exists!")
            return redirect("mechanic_register")

        # 1. Create USER
        user = User.objects.create_user(
            email=email,
            phone=phone,
            password=password,
            username=email,        # optional
            user_type="mechanic"   # IMPORTANT
        )

        # Add full name
        user.first_name = name
        user.save()

        # 2. Create Mechanic Profile
        mech_profile = Mechanic.objects.create(
            user=user,
            approval_status="pending"
        )

        # 3. Save documents
        MechanicDocument.objects.create(
            mechanic=mech_profile,
            document_type="id_card",
            document_file=cnic_front
        )
        MechanicDocument.objects.create(
            mechanic=mech_profile,
            document_type="id_card",
            document_file=cnic_back
        )

        messages.success(request, "Account created! Wait for admin approval.")
        return redirect("login_view")

    return render(request, "karigar_app/login.html")

def client_register(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")

        username = email.split("@")[0]

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists!")
            return redirect('login_view')

        if User.objects.filter(phone=phone).exists():
            messages.error(request, "Phone already exists!")
            return redirect('login_view')

        user = User.objects.create(
            username=username,
            email=email,
            phone=phone,
            password=make_password(password),
            is_mechanic=False
        )

        User.objects.create(user=user)

        messages.success(request, "Client registered successfully!")
        return redirect('login_view')

    return redirect('login_view')

def search(request):
    query = request.GET.get("q", "")

    results = Mechanic.objects.filter(
        Q(user__username__icontains=query) |
        Q(bio__icontains=query)
    )

    return render(request, "karigar_app/search.html", {
        "query": query,
        "results": results
    })

def privacy_policy(request):
    return render(request, 'karigar_app/privacy.html')
def terms_and_conditions(request):
    return render(request, 'karigar_app/terms.html')
def logout_view(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('index')

@login_required
def mechanic_dashboard(request):
    user = request.user
    if not user.is_mechanic:
        return redirect('index' ,{"message": "Access denied."})

    mechanic_profile = user.mechanic_profile

    # Upcoming Jobs: assigned but not yet completed
    upcoming_jobs = ServiceRequest.objects.filter(
        mechanic=mechanic_profile,
        status__in=['assigned', 'in_progress']
    ).select_related('job', 'job__customer').order_by('job__preferred_time')
    upcoming_jobs_count = upcoming_jobs.count()

    # Pending Requests: jobs that are open or quoted but not assigned
    pending_requests_count = ServiceRequest.objects.filter(
        status__in=['open', 'quoted']
    ).exclude(
        assignment__mechanic=mechanic_profile
    ).count()

    # Earnings: sum of completed jobs mechanic_payout
    completed_payments = Transaction.objects.filter(
        job__assignment__mechanic=mechanic_profile,
        status='succeeded'
    )
    total_earnings = completed_payments.aggregate(total=Sum('mechanic_payout'))['total'] or 0

    # Average rating
    avg_rating = Review.objects.filter(mechanic=mechanic_profile).aggregate(avg=Avg('score'))['avg'] or 0

    # Recent Jobs: last 5 jobs assigned
    recent_jobs = ServiceRequest.objects.filter(
        mechanic=mechanic_profile
    ).select_related('job', 'job__customer', 'job__service_type').order_by('-assigned_at')[:5]

    context = {
        'upcoming_jobs_count': upcoming_jobs_count,
        'pending_requests_count': pending_requests_count,
        'total_earnings': total_earnings,
        'average_rating': round(avg_rating, 1),
        'recent_jobs': recent_jobs,
    }

    return render(request, 'karigar_app/mechanic_dash.html', context)

# ============================================================================
# 1. AUTHENTICATION AND USER VIEWS (Welcome / Sign Up Flow)
# ============================================================================
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

class AuthViewSet(viewsets.ViewSet):
    """
    Handles user registration, login, and token management.
    """
    permission_classes = [permissions.AllowAny]

    def generate_tokens(self, user):
        """Create JWT tokens for a user"""
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }

    @action(detail=False, methods=['post'])
    def register(self, request):
        """Screen: Sign Up - Create Account"""
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.save()

        # Generate JWT tokens
        tokens = self.generate_tokens(user)

        return Response({
            "user": UserSerializer(user).data,
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "message": "Registration successful."
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def login(self, request):
        """Screen: Login"""
        serializer = UserLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']

        # Generate JWT tokens
        tokens = self.generate_tokens(user)

        return Response({
            "user": UserSerializer(user).data,
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "message": "Login successful"
        }, status=status.HTTP_200_OK)

class UserProfileViewSet(viewsets.ModelViewSet):
    """
    Handles user profile retrieval and updates. (Common in both: Profile screens)
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        if self.request.user.is_staff:
            return User.objects.all()
        return User.objects.filter(id=self.request.user.id)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request, pk=None):
        """Screen: Common in both - Change Password"""
        user = self.get_object()
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'status': 'password set'}, status=status.HTTP_200_OK)
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request, pk=None):
        """Screen: Common in both - Change Password"""
        user = self.get_object()
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'status': 'password set'}, status=status.HTTP_200_OK)

# ============================================================================
# 2. CUSTOMER FLOW VIEWS (Customer Dashboard)
# ============================================================================

class VehicleViewSet(viewsets.ModelViewSet):
    """
    Manages customer vehicles. (Customer Dashboard: Vehicle selection)
    """
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.role == 'customer':
            return Vehicle.objects.filter(customer=self.request.user)
        return Vehicle.objects.none()

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)

    @action(detail=False, methods=['get'])
    def default(self, request):
        """Get the customer's default vehicle."""
        default_vehicle = self.get_queryset().filter(is_default=True).first()
        if default_vehicle:
            serializer = self.get_serializer(default_vehicle)
            return Response(serializer.data)
        return Response({'detail': 'No default vehicle found.'}, status=status.HTTP_404_NOT_FOUND)


class MechanicViewSet(viewsets.ModelViewSet):
    """
    Handles mechanic profile management and listing for customers.
    """
    queryset = Mechanic.objects.all()
    serializer_class = MechanicSerializer
    permission_classes = [IsAdminOrReadOnly] 

    def get_queryset(self):
        # Customers should only see active, available mechanics
        if self.request.user.role == 'customer':
            return Mechanic.objects.available().top_rated()
        return Mechanic.objects.all() # Admin/Mechanic view

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsCustomer])
    def nearby(self, request):
        """Screen: Customer Dashboard - Map view (finding nearby mechanics)"""
        latitude = request.query_params.get('lat')
        longitude = request.query_params.get('lon')
        radius = request.query_params.get('radius', 15)

        if not latitude or not longitude:
            return Response({"detail": "lat and lon query parameters are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Assuming the custom manager method 'nearby' returns a list of (mechanic, distance) tuples
        nearby_mechanics_data = Mechanic.objects.nearby(float(latitude), float(longitude), int(radius))
        mechanics = [item[0] for item in nearby_mechanics_data]
        
        # Note: The serializer should handle the 'distance_km' field based on the custom manager logic
        serializer = self.get_serializer(mechanics, many=True)
        
        return Response(serializer.data)


class ServiceRequestViewSet(viewsets.ModelViewSet):
    """
    Handles service request creation, management, and status updates.
    (Customer Dashboard: Request form, Mechanic Dashboard: Task list)
    """
    queryset = ServiceRequest.objects.all()
    serializer_class = ServiceRequestSerializer

    def get_permissions(self):
        if self.action in ['create']:
            self.permission_classes = [permissions.IsAuthenticated, IsCustomer]
        elif self.action in ['accept']:
            # Mechanic must be authenticated and a mechanic, but not yet assigned to the request
            self.permission_classes = [permissions.IsAuthenticated, IsMechanic]
        elif self.action in ['reject', 'start', 'complete', 'add_item', 'update_location']:
            # These actions require the mechanic to be already assigned
            self.permission_classes = [permissions.IsAuthenticated, IsAssignedMechanic]
        elif self.action in ['retrieve', 'list']:
            self.permission_classes = [permissions.IsAuthenticated, IsServiceRequestOwner]
        elif self.action in ['cancel']:
            self.permission_classes = [permissions.IsAuthenticated, IsServiceRequestOwner]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'create':
            return ServiceRequestCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ServiceRequestUpdateSerializer
        return ServiceRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'customer':
            return ServiceRequest.objects.by_customer(user)
        elif user.role == 'mechanic':
            # Mechanic sees requests assigned to them AND pending requests they can accept
            return ServiceRequest.objects.filter(Q(mechanic=user) | Q(status='pending')).distinct()
        return ServiceRequest.objects.all() # Admin view

    def perform_create(self, serializer):
        """Screen: Customer Dashboard - Request form submission"""
        serializer.save(customer=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsMechanic])
    def accept(self, request, pk=None):
        """Mechanic accepts a pending service request"""
        service_request = self.get_object()
        estimated_arrival = request.data.get('estimated_arrival_minutes')

        from django.utils import timezone
        from datetime import timedelta
        
        # Check for expiration (30 seconds)
        if (timezone.now() - service_request.created_at) > timedelta(seconds=30):
            return Response({"detail": "This service request has expired and is no longer available."}, status=status.HTTP_400_BAD_REQUEST)

        if service_request.status != 'pending':
            return Response({"detail": "This service request is not pending."}, status=status.HTTP_400_BAD_REQUEST)
        
        if service_request.mechanic is not None:
            return Response({"detail": "This service request has already been accepted."}, status=status.HTTP_400_BAD_REQUEST)

        if not estimated_arrival:
            return Response({"detail": "estimated_arrival_minutes is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Assign the mechanic (must be User) and change status
        # NOTE: Assuming service_request.accept(user, estimated_arrival) exists and handles status change and assignment
        service_request.mechanic = request.user
        service_request.status = 'accepted'
        service_request.estimated_arrival_time = estimated_arrival
        service_request.save()
        
        # You might need to call a method on the model if it handles more logic
        # service_request.accept(request.user, estimated_arrival)

        return Response(ServiceRequestSerializer(service_request).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAssignedMechanic])
    def start(self, request, pk=None):
        """Screen: Service Completion Flow - Start Service"""
        service_request = self.get_object()
        service_request.start_service() # Assuming start_service() method exists on the model
        return Response(ServiceRequestSerializer(service_request).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAssignedMechanic])
    def complete(self, request, pk=None):
        """Screen: Service Completion Flow - Finalize Invoice/Completion"""
        service_request = self.get_object()
        service_request.complete() # Assuming complete() method exists on the model
        return Response(ServiceRequestSerializer(service_request).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsServiceRequestOwner])
    def cancel(self, request, pk=None):
        """Screen: Customer Dashboard / Mechanic Dashboard - Cancel Request"""
        service_request = self.get_object()
        reason = request.data.get('reason', 'No reason provided.')
        cancelled_by = self.request.user.role
        
        service_request.cancel(cancelled_by, reason) # Assuming cancel() method exists on the model
        return Response(ServiceRequestSerializer(service_request).data)


# ============================================================================
# 3. MECHANIC FLOW VIEWS (Mechanic Profile Building & Dashboard)
# ============================================================================

class MechanicProfileViewSet(viewsets.ModelViewSet):
    """
    Handles mechanic profile updates. (Mechanic Profile Building)
    """
    queryset = Mechanic.objects.all()
    serializer_class = MechanicUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsMechanicOwner]

    def get_queryset(self):
        # Only allow mechanic to view/edit their own profile
        if self.request.user.role == 'mechanic':
            return Mechanic.objects.filter(user=self.request.user)
        return Mechanic.objects.none()

    def get_object(self):
        # Retrieve the mechanic profile linked to the current user
        return get_object_or_404(Mechanic, user=self.request.user)

    
    @action(detail=False, methods=['post'])
    def toggle_availability(self, request):
        """Screen: Mechanic Dashboard - Toggle Availability"""
        mechanic = self.get_object()
        mechanic.is_available = not mechanic.is_available
        mechanic.save()
        return Response({'is_available': mechanic.is_available}, status=status.HTTP_200_OK)


class MechanicDocumentViewSet(viewsets.ModelViewSet):
    """
    Handles document uploads for mechanics. (Mechanic Profile Building: Documents)
    """
    serializer_class = MechanicDocumentSerializer
    permission_classes = [permissions.IsAuthenticated, IsMechanic]

    def get_queryset(self):
        return MechanicDocument.objects.filter(mechanic__user=self.request.user)

    def perform_create(self, serializer):
        mechanic = get_object_or_404(Mechanic, user=self.request.user)
        serializer.save(mechanic=mechanic)


class MechanicServiceViewSet(viewsets.ModelViewSet):
    """
    Allows mechanics to manage their service offerings. (Mechanic Profile Building: Services)
    """
    serializer_class = MechanicServiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsMechanic]

    def get_queryset(self):
        if self.request.user.role == 'mechanic':
            try:
                mechanic_profile = self.request.user.mechanic_profile
                return MechanicService.objects.filter(mechanic=mechanic_profile)
            except Exception:
                return MechanicService.objects.none()
        return MechanicService.objects.none()

    def perform_create(self, serializer):
        mechanic_profile = self.request.user.mechanic_profile
        serializer.save(mechanic=mechanic_profile)


class ServiceRequestItemViewSet(viewsets.ModelViewSet):
    """
    Manages line items within a specific ServiceRequest. (Service Completion Flow: Add/Edit Items)
    """
    serializer_class = ServiceRequestItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsMechanic]

    def get_queryset(self):
        # This view is intended to be nested under ServiceRequest
        request_id = self.kwargs.get('service_request_pk')
        if not request_id:
            return ServiceRequestItem.objects.none()

        try:
            service_request = ServiceRequest.objects.get(id=request_id)
            if service_request.mechanic == self.request.user:
                return ServiceRequestItem.objects.filter(service_request=service_request)
        except ServiceRequest.DoesNotExist:
            pass
        
        return ServiceRequestItem.objects.none()

    def perform_create(self, serializer):
        request_id = self.kwargs.get('service_request_pk')
        service_request = get_object_or_404(ServiceRequest, id=request_id)
        
        if service_request.mechanic != self.request.user:
            raise permissions.PermissionDenied("You are not the assigned mechanic for this service request.")

        serializer.save(service_request=service_request)

# ============================================================================
# 4. COMMON AND OTHER VIEWS
# ============================================================================

class ReviewViewSet(viewsets.ModelViewSet):
    """
    Handles reviews and ratings. (Service Completion Flow: Rating screen)
    """
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        # Allow filtering by reviewee (mechanic/customer)
        reviewee_id = self.request.query_params.get('reviewee')
        if reviewee_id:
            return Review.objects.filter(reviewee_id=reviewee_id)
        return Review.objects.all()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsMechanic])
    def respond(self, request, pk=None):
        """Mechanic response to a review."""
        review = self.get_object()
        serializer = ReviewResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Assuming ReviewResponse model exists and links to Review
        ReviewResponse.objects.create(
            review=review,
            mechanic=self.request.user,
            response_text=serializer.validated_data['response_text']
        )
        return Response({'status': 'response recorded'}, status=status.HTTP_201_CREATED)


class ChatSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles chat sessions. (Common in both: Chat screen)
    """
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter messages for the current user in a specific session
        session_id = self.kwargs.get('session_pk')
        if session_id:
            return ChatMessage.objects.filter(session_id=session_id).order_by('created_at')
        return ChatMessage.objects.none()


class ServiceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for canonical service types. Read-only for all users.
    """
    queryset = ServiceType.objects.filter(is_active=True)
    serializer_class = ServiceTypeSerializer
    permission_classes = [permissions.AllowAny]


class PromotionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles listing of active promotions. (Customer Dashboard: Promotions)
    """
    queryset = Promotion.objects.filter(is_active=True)
    serializer_class = PromotionSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def apply(self, request):
        """Apply a promotion code to a service request."""
        code = request.data.get('code')
        service_request_id = request.data.get('service_request_id')
        
        # Logic to validate and apply promotion to the service request
        # ...
        
        return Response({'status': 'promotion applied', 'discount_amount': Decimal('10.00')})


class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles user wallet balance. (Customer Dashboard: Wallet)
    """
    queryset = Wallet.objects.all()
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOwnerOrReadOnly])
    def withdraw(self, request, pk=None):
        """Withdraw funds from wallet."""
        wallet = self.get_object()
        amount = request.data.get('amount')
        # Logic to handle withdrawal
        # ...
        return Response({'status': 'withdrawal initiated'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOwnerOrReadOnly])
    def top_up(self, request, pk=None):
        """Top up wallet funds."""
        wallet = self.get_object()
        amount = request.data.get('amount')
        # Logic to handle top-up
        # ...
        return Response({'status': 'top-up initiated'})

# In emechanics/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Webhook # Assuming you created the model

@api_view(['POST'])
@permission_classes([AllowAny])
def uuid_webhook_receiver(request, webhook_uuid):
    """
    Receives a payload from a third-party service using a UUID in the URL.
    The URL format will be: /api/v1/webhooks/{webhook_uuid}/
    """
    try:
        # 1. Look up the webhook configuration using the UUID
        webhook_config = get_object_or_404(Webhook, id=webhook_uuid, is_active=True)
    except Exception:
        # Return a generic 404 or 400 to prevent enumeration attacks
        return Response({"detail": "Invalid webhook endpoint."}, status=status.HTTP_404_NOT_FOUND)

    # 2. Process the incoming payload based on the event type
    payload = request.data # The data sent by the third-party service

    if webhook_config.event_type == 'payment_success':
        # Example: Update the status of a transaction
        # transaction_id = payload.get('transaction_ref')
        # Transaction.objects.filter(reference_number=transaction_id).update(status='completed')
        print(f"Processing Payment Success for: {webhook_config.user.email}")
        
    elif webhook_config.event_type == 'mechanic_status':
        # Example: Update mechanic's availability
        # mechanic = webhook_config.user.mechanic_profile
        # mechanic.is_available = payload.get('is_available')
        # mechanic.save()
        print(f"Processing Mechanic Status for: {webhook_config.user.email}")
        
    # 3. Return a 200 OK response to the sender
    return Response({"status": "success", "message": "Payload received and processed."}, status=status.HTTP_200_OK)
