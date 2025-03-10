from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import Order


@receiver(user_logged_in)
def merge_carts(sender, user, request, **kwargs):
    session_key = request.session.session_key
    if not session_key:
        return

    # Get existing orders
    guest_order = Order.objects.filter(session_key=session_key, ordered=False).first()
    user_order = Order.objects.filter(user=user, ordered=False).first()

    if not guest_order:
        return

    if not user_order:
        # Convert guest order to user order
        guest_order.user = user
        guest_order.session_key = None
        guest_order.save()
    else:
        # Merge items from guest cart to user cart
        for guest_item in guest_order.order_items.all():
            item_exists = user_order.order_items.filter(
                item=guest_item.item,
                color=guest_item.color
            ).exists()

            if item_exists:
                user_item = user_order.order_items.get(
                    item=guest_item.item,
                    color=guest_item.color
                )
                user_item.quantity += guest_item.quantity
                user_item.save()
            else:
                guest_item.order = user_order
                guest_item.save()

        # Delete guest order after merging
        guest_order.delete()

    # Update session
    request.session['cart_item_count'] = user_order.order_items.count()
    request.session.modified = True