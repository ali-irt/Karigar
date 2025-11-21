# emechanics/serializers.py
from rest_framework import serializers
from .models import JobRequest, Quote, MechanicProfile, ServiceType, Vehicle, Location, JobAssignment, Payment

class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = ['id', 'slug', 'title', 'base_price', 'base_duration_minutes']

class MechanicProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MechanicProfile
        fields = ['id', 'user', 'bio', 'is_available', 'rating', 'rating_count', 'hourly_base']

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'point', 'address', 'name']

class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['id', 'owner', 'make', 'model', 'year', 'plate_number']

class JobRequestSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    pickup_location = LocationSerializer()
    class Meta:
        model = JobRequest
        fields = ['id','customer','vehicle','service_type','description','pickup_location',
                  'preferred_time','status','final_price','estimated_duration_minutes','created_at']

    def create(self, validated_data):
        loc_data = validated_data.pop('pickup_location', None)
        if loc_data:
            loc = Location.objects.create(**loc_data)
            validated_data['pickup_location'] = loc
        user = self.context['request'].user
        validated_data['customer'] = user
        return super().create(validated_data)

class QuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = ['id','job','mechanic','price','estimated_duration_minutes','expires_at','accepted','created_at']

class JobAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobAssignment
        fields = ['id','job','mechanic','assigned_at','accepted_at','arrived_at','started_at','finished_at','status']
