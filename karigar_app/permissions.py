from rest_framework import permissions
from django.shortcuts import get_object_or_404
from .models import ServiceRequest # Import ServiceRequest model for checks

# ============================================================================
# ROLE-BASED PERMISSIONS
# ============================================================================

class IsCustomer(permissions.BasePermission):
    """
    Custom permission to only allow customers to access.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'customer'

class IsMechanic(permissions.BasePermission):
    """
    Custom permission to only allow mechanics to access.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'mechanic'

class IsAdmin(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to edit, but read access for all.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'admin'

# ============================================================================
# OBJECT-LEVEL PERMISSIONS (Owner/Assigned)
# ============================================================================

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    Assumes the model instance has a 'user' or 'customer' field.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Check for 'user' field (e.g., UserProfile, Wallet, Preference)
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # Check for 'customer' field (e.g., Vehicle)
        if hasattr(obj, 'customer'):
            return obj.customer == request.user
            
        return False

class IsMechanicOwner(permissions.BasePermission):
    """
    Custom permission to only allow the mechanic who owns the profile to edit it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # obj is the Mechanic profile instance
        return obj.user == request.user

class IsCustomerOwner(permissions.BasePermission):
    """
    Custom permission to only allow the customer who owns the object to access it.
    """
    def has_object_permission(self, request, view, obj):
        # Assumes the object has a 'customer' field (e.g., Vehicle)
        return obj.customer == request.user

class IsServiceRequestOwner(permissions.BasePermission):
    """
    Custom permission to allow the customer OR the assigned mechanic to access the request.
    """
    def has_object_permission(self, request, view, obj):
        # obj is the ServiceRequest instance
        is_customer = obj.customer == request.user
        is_mechanic = obj.mechanic == request.user
        is_admin = request.user.role == 'admin'
        
        return is_customer or is_mechanic or is_admin

class IsAssignedMechanic(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if view.action == 'accept':
            return request.user.role == 'mechanic' and obj.mechanic is None
        return obj.mechanic == request.user
