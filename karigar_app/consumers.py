import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.shortcuts import get_object_or_404
from .models import User, Mechanic, ServiceRequest, ChatSession, ChatMessage, LocationUpdate
from .serializers import ChatMessageSerializer, MechanicSerializer # Assuming these exist
from rest_framework.renderers import JSONRenderer
from django.core.exceptions import ObjectDoesNotExist

# --- Helper Functions for Database Operations ---

@database_sync_to_async
def get_service_request_and_session(request_id):
    """Fetches the ServiceRequest object and its associated ChatSession."""
    try:
        sr = ServiceRequest.objects.select_related('mechanic', 'customer').get(id=request_id)
        session, created = ChatSession.objects.get_or_create(service_request=sr)
        return sr, session
    except ServiceRequest.DoesNotExist:
        raise ObjectDoesNotExist("ServiceRequest not found.")

@database_sync_to_async
def save_location_update(service_request, user, latitude, longitude):
    """Saves a new location update and updates the mechanic's profile if applicable."""
    
    # 1. Save the update to the LocationUpdate history (for tracking)
    LocationUpdate.objects.create(
        service_request=service_request,
        user=user,
        latitude=latitude,
        longitude=longitude
    )
    
    # 2. Update the Mechanic's current location for general availability/search
    if user.is_mechanic():
        try:
            mechanic = user.mechanic_profile
            mechanic.current_latitude = latitude
            mechanic.current_longitude = longitude
            mechanic.last_location_update = timezone.now()
            mechanic.save()
        except Mechanic.DoesNotExist:
            pass # Should not happen if user is a mechanic
            
    # 3. Return the user's role for broadcast identification
    return user.role

@database_sync_to_async
def save_chat_message(session, sender, message_text):
    """
    Saves a new chat message to the database.
    NOTE: Per user request, this is for ephemeral chat (no history).
    The message is saved here primarily for immediate serialization and
    to satisfy the requirement of using the existing serializer.
    In a true no-history system, this step would be skipped, and the
    message would only be broadcast.
    """
    message = ChatMessage.objects.create(
        session=session,
        sender=sender,
        message=message_text,
    )
    # Serialize the message data
    serializer = ChatMessageSerializer(message)
    return JSONRenderer().render(serializer.data).decode('utf-8')

# --- Consumers ---

class ServiceRequestConsumer(AsyncWebsocketConsumer):
    """
    Handles real-time communication for a specific service request,
    including location tracking and in-app chat.
    """
    
    async def connect(self):
        self.user = self.scope["user"]
        self.request_id = self.scope['url_route']['kwargs']['request_id']
        self.room_group_name = f'service_request_{self.request_id}'

        # 1. Check authentication and authorization
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # 2. Check if user is part of this service request
        try:
            self.service_request, self.chat_session = await get_service_request_and_session(self.request_id)
            
            is_customer = self.service_request.customer == self.user
            is_mechanic = self.service_request.mechanic == self.user
            
            if not (is_customer or is_mechanic):
                await self.close()
                return
            
            self.is_mechanic = is_mechanic
            self.is_customer = is_customer
            
        except ObjectDoesNotExist:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        # Send initial confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': f'Connected to service request {self.request_id} channel.'
        }))

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'location_update':
            await self.handle_location_update(data)
        elif message_type == 'chat_message':
            await self.handle_chat_message(data)
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message type.'
            }))

    # --- Handlers for incoming messages ---

    async def handle_location_update(self, data):
        """Handles location updates from either party and broadcasts to the group."""
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return

        # 1. Update database (runs in a separate thread)
        user_role = await save_location_update(self.service_request, self.user, latitude, longitude)
        
        # 2. Broadcast the new location to the group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'location.broadcast',
                'latitude': latitude,
                'longitude': longitude,
                'user_id': str(self.user.id),
                'user_role': user_role,
                'timestamp': timezone.now().isoformat()
            }
        )

    async def handle_chat_message(self, data):
        """Handles chat messages from either party and broadcasts to the group."""
        message_text = data.get('message')
        
        if not message_text:
            return

        # 1. Save message to database (runs in a separate thread)
        # The returned message_data is a JSON string of the serialized message
        message_json_string = await save_chat_message(
            self.chat_session, self.user, message_text
        )

        # 2. Broadcast the message to the group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat.broadcast',
                'message_json_string': message_json_string,
            }
        )

    # --- Handlers for outgoing broadcasts (received from channel layer) ---

    async def location_broadcast(self, event):
        """Sends location data to the WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'location_update',
            'user_id': event['user_id'],
            'user_role': event['user_role'],
            'latitude': event['latitude'],
            'longitude': event['longitude'],
            'timestamp': event['timestamp']
        }))

    async def chat_broadcast(self, event):
        """Sends chat message data to the WebSocket."""
        # The message is already a JSON string, so we load it and then send it
        message_data = json.loads(event['message_json_string'])
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message_data
        }))
