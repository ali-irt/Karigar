# emechanics/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import JobRequest, Quote, MechanicProfile, JobAssignment, ServiceType
from .serializers import JobRequestSerializer, QuoteSerializer, MechanicProfileSerializer, JobAssignmentSerializer
from . import serializers
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.shortcuts import redirect, render

from django.db.models import Q
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
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from .models import User, MechanicProfile, MechanicDocument

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
        mech_profile = MechanicProfile.objects.create(
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

        CustomerProfile.objects.create(user=user)

        messages.success(request, "Client registered successfully!")
        return redirect('login_view')

    return redirect('login_view')

def search(request):
    query = request.GET.get("q", "")

    results = MechanicProfile.objects.filter(
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

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Sum
from .models import JobRequest, JobAssignment, Payment, Rating

@login_required
def mechanic_dashboard(request):
    user = request.user
    if not user.is_mechanic:
        return redirect('index' ,{"message": "Access denied."})

    mechanic_profile = user.mechanic_profile

    # Upcoming Jobs: assigned but not yet completed
    upcoming_jobs = JobAssignment.objects.filter(
        mechanic=mechanic_profile,
        status__in=['assigned', 'in_progress']
    ).select_related('job', 'job__customer').order_by('job__preferred_time')
    upcoming_jobs_count = upcoming_jobs.count()

    # Pending Requests: jobs that are open or quoted but not assigned
    pending_requests_count = JobRequest.objects.filter(
        status__in=['open', 'quoted']
    ).exclude(
        assignment__mechanic=mechanic_profile
    ).count()

    # Earnings: sum of completed jobs mechanic_payout
    completed_payments = Payment.objects.filter(
        job__assignment__mechanic=mechanic_profile,
        status='succeeded'
    )
    total_earnings = completed_payments.aggregate(total=Sum('mechanic_payout'))['total'] or 0

    # Average rating
    avg_rating = Rating.objects.filter(mechanic=mechanic_profile).aggregate(avg=Avg('score'))['avg'] or 0

    # Recent Jobs: last 5 jobs assigned
    recent_jobs = JobAssignment.objects.filter(
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
