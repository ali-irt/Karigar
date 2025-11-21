# emechanics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import MechanicProfile, JobRequest, Rating  # assume Rating exists or map to existing model
from django.contrib.auth import get_user_model
import django.db.models as models
User = get_user_model()

@receiver(post_save, sender=User)
def create_profiles_on_user_create(sender, instance, created, **kwargs):
    if created:
        # create customer profile implicitly (you can have explicit CustomerProfile too)
        # create mechanic profile only if user.is_mechanic set true
        if getattr(instance, 'is_mechanic', False):
            MechanicProfile.objects.get_or_create(user=instance)

# incremental rating update (assume Rating model)
@receiver(post_save, sender='emechanics.Rating')
def update_mechanic_rating_on_new_rating(sender, instance, created, **kwargs):
    if not created:
        return
    mech = instance.mechanic
    # atomic-ish update using DB expressions to avoid race
    from django.db.models import F
    mech.rating_count = F('rating_count') + 1
    # update rating as (old*count + new)/new_count
    # compute via raw SQL expression: new_rating = ((rating * (count)) + score) / (count + 1)
    # we perform two-step update to avoid floating race; after F() updates, refresh
    mech.save(update_fields=['rating_count'])
    mech.refresh_from_db()
    # safe recompute using aggregates (rare, but correct)
    agg = mech.ratings.aggregate(total=models.Sum('score'))
    total = agg['total'] or 0
    mech.rating = total / mech.rating_count if mech.rating_count else 0
    mech.save(update_fields=['rating'])
