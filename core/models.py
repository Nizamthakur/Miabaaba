from django.db.models.signals import post_save
from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.shortcuts import reverse
from django_countries.fields import CountryField
from django.utils import timezone
from datetime import timedelta
from django.core.validators import RegexValidator, MinValueValidator
from decimal import Decimal
from django.contrib.auth.models import AbstractUser, BaseUserManager



LABEL_CHOICES = (
    ('P', 'newest arrival'),
    ('S', 'customer\'s choice'),
    ('D', 'Limited Stock')
)

ADDRESS_CHOICES = (
    ('B', 'Billing'),
    ('S', 'Shipping'),
)

from django.contrib.auth.models import AbstractUser, BaseUserManager


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

class UserProfile(models.Model):
    user = models.OneToOneField(
        'core.User', on_delete=models.CASCADE)
    stripe_customer_id = models.CharField(max_length=50, blank=True, null=True)
    one_click_purchasing = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('product_list', kwargs={'slug': self.slug})


class Subcategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey('Category', on_delete=models.CASCADE, related_name='subcategories')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("core:subcategory_list", kwargs={'slug': self.category.slug, 'subcategory_slug': self.slug})


class ProductImage(models.Model):
    item = models.ForeignKey('Item', related_name='additional_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='product_images/')
    alt_text = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Image for {self.item.title}"


class Color(models.Model):
    name = models.CharField(max_length=50, unique=True)
    hex_value = models.CharField(max_length=7, blank=True, null=True)

    def __str__(self):
        return self.name


class Item(models.Model):
    title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # Change to DecimalField
    original_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # Add this line
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # Change to DecimalField
    category = models.ForeignKey('Category', on_delete=models.CASCADE, related_name="items")
    subcategory = models.ForeignKey('Subcategory', on_delete=models.CASCADE, related_name='items', blank=True,
                                    null=True)
    label = models.CharField(choices=LABEL_CHOICES, max_length=1)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    image = models.ImageField()
    product_code = models.CharField(max_length=50, unique=True, blank=True, null=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core:product", kwargs={'slug': self.slug})

    def get_add_to_cart_url(self):
        return reverse("core:add-to-cart", kwargs={'slug': self.slug})

    def get_remove_from_cart_url(self):
        return reverse("core:remove-from-cart", kwargs={'slug': self.slug})

class ItemVariant(models.Model):
    item = models.ForeignKey(Item, related_name='variants', on_delete=models.CASCADE)
    color = models.ForeignKey(Color, related_name='variants', on_delete=models.CASCADE)
    quantity_in_stock = models.PositiveIntegerField(default=0)

    def __str__(self):
        color_name = self.color.name if self.color else "No Color"  # Handle case where color is None
        return f"{self.item.title} - {color_name}"

class OrderItem(models.Model):
    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name="order_items",
        null=True,
        blank=True
    )
    item = models.ForeignKey('Item', related_name='order_items', on_delete=models.CASCADE)
    item_name = models.CharField(max_length=100, default='Unnamed Item')
    ordered = models.BooleanField(default=False)
    quantity = models.PositiveIntegerField(default=1)
    color = models.ForeignKey('Color', on_delete=models.CASCADE, default=1)
    moved_to_order = models.BooleanField(default=False)
    item_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)  # Price at time of purchase
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    amount_saved = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def __str__(self):
        order_info = f"Order {self.order.id}" if self.order else "No Order"
        return f"{self.quantity}x {self.item.title} ({self.color}) - {order_info}"

    def get_current_price(self):
        """Get the effective price (discounted if available)"""
        return self.item.discount_price if self.item.discount_price else self.item.price

    def get_total_item_price(self):
        """Calculate total price for this item"""
        if self.item.discount_price:
            return self.quantity * self.item.discount_price
        return self.quantity * self.item.price

    def get_regular_total_price(self):
        """Calculate total without discount"""
        return self.quantity * self.item.price

    def get_amount_saved(self):
        """Calculate savings per item"""
        if self.item.discount_price:
            return (self.item.price - self.item.discount_price) * self.quantity
        return Decimal('0.00')

    def get_price_breakdown(self):
        """Get formatted price information"""
        if self.item.discount_price:
            return {
                'original_price': self.item.price,
                'discounted_price': self.item.discount_price,
                'total_saved': self.get_amount_saved(),
                'has_discount': True
            }
        return {
            'price': self.item.price,
            'has_discount': False
        }

    def get_total_discount_item_price(self):
        """Calculate the total price for this order item after applying discounts."""
        item_price = self.get_current_price()  # Use the current price method
        return item_price * self.quantity

    def get_final_price(self):
        """Return the final price for this order item."""
        return self.get_total_discount_item_price()

    def save(self, *args, **kwargs):
        """Automatically set prices when saving"""
        if not self.original_price:
            self.original_price = self.item.price
        if not self.item_price:
            self.item_price = self.item.discount_price or self.item.price
        super().save(*args, **kwargs)
class OrderManager(models.Manager):
    def get_for_user(self, request):
        if not request.session.session_key:
            request.session.create()

        # For authenticated users
        if request.user.is_authenticated:
            return self.filter(
                user=request.user,
                ordered=False
            ).prefetch_related('order_items').first()

        # For anonymous users
        return self.filter(
            session_key=request.session.session_key,
            ordered=False
        ).prefetch_related('order_items').first()

class Order(models.Model):
    objects = OrderManager()
    PAYMENT_CHOICES = [
        ('cash_on_delivery', 'Cash on Delivery'),
        ('bikash', 'Bikash'),
        ('nagad', 'Nagad'),
    ]


    ORDER_CHANNEL_CHOICES = [
        ('facebook', 'Facebook'),
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('tiktok', 'TikTok'),
        ('website', 'Website'),
        ('in_house', 'In House'),
    ]


    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_review', 'In Review'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('partial_delivered', 'Partially Delivered'),
        ('cancelled', 'Cancelled'),
        ('hold', 'On Hold'),
        ('unknown', 'Unknown Status'),
    ]



    order_channel = models.CharField(max_length=20, choices=ORDER_CHANNEL_CHOICES, default='website')
    shipping_name = models.CharField(max_length=255, blank=True, null=True)
    user = models.ForeignKey(
        'core.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    session_key = models.CharField(max_length=40, blank=True, null=True)
    ref_code = models.CharField(max_length=20, blank=True, null=True)
    start_date = models.DateTimeField(auto_now_add=True, editable=False)
    ordered_date = models.DateTimeField(auto_now=True)
    ordered = models.BooleanField(default=False)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_address = models.ForeignKey('Address', related_name='shipping_address', on_delete=models.SET_NULL,
                                         blank=True, null=True)
    billing_address = models.ForeignKey('Address', related_name='billing_address', on_delete=models.SET_NULL,
                                        blank=True, null=True)
    email = models.EmailField(null=True, blank=True)
    guest_checkout = models.BooleanField(default=False)
    phone_number = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                r'^01[3-9]\d{8}$',
                'Enter a valid Bangladeshi phone number starting with 01'
            )
        ],
        blank=True,
        null=True
    )
    shipping_thana = models.CharField(max_length=255, blank=True, null=True)
    shipping_zip = models.CharField(max_length=20, blank=True, null=True)
    billing_country = models.CharField(max_length=100, blank=True, null=True)
    billing_thana = models.CharField(max_length=255, blank=True, null=True)
    shipping_country = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash_on_delivery')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    bikash_nagad_number = models.CharField(max_length=20, blank=True, null=True)
    payment = models.ForeignKey('Payment', on_delete=models.SET_NULL, blank=True, null=True)
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, blank=True, null=True)
    being_delivered = models.BooleanField(default=False)
    received = models.BooleanField(default=False)
    refund_requested = models.BooleanField(default=False)
    refund_granted = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    call_count = models.IntegerField(default=0)
    verification_note = models.TextField(blank=True, null=True)
    consignment_id = models.CharField(max_length=50, blank=True, null=True)
    tracking_code = models.CharField(max_length=50, blank=True, null=True)
    delivery_status = models.CharField(
        max_length=50,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending'
    )
    steadfast_data = models.JSONField(blank=True, null=True)

    def __str__(self):
        identifier = self.user.username if self.user else self.session_key
        return f"Order #{self.get_invoice_id()} - {identifier}"

    # Coupon methods (keep existing)
    def is_coupon_valid(self):
        return bool(self.coupon and self.coupon.is_valid())

    def get_amount_saved(self):
        if self.is_coupon_valid():
            coupon = self.coupon
            total = self.get_total_without_coupon()
            if coupon.discount_type == 'fixed':
                return Decimal(coupon.amount)
            return total * (Decimal(coupon.amount) / Decimal(100))
        return Decimal('0.00')

    # Total calculation (optimized)
    def get_total_without_coupon(self):
        """Sum of ALL item totals (with discounts)"""
        return sum(item.get_total_item_price() for item in self.order_items.all())

    def get_total(self):
        """Final total after coupons + delivery"""
        total = self.get_total_without_coupon()
        # Apply coupon discount
        if self.coupon and self.coupon.is_valid():
            total -= self.get_amount_saved()

        # Add delivery charge
        return total + Decimal(self.delivery_charge)

    def get_amount_saved(self):
        """Calculate coupon savings"""
        if self.coupon:
            if self.coupon.discount_type == 'fixed':
                return Decimal(self.coupon.amount)
            return sum(
                item.get_total_item_price()
                for item in self.order_items.all()
            ) * (Decimal(self.coupon.amount) / Decimal(100))
        return Decimal(0)

    # Steadfast integration methods
    def get_invoice_id(self):
        return f"ORD-{self.id:08d}-{self.start_date.strftime('%y%m%d')}"

    def get_tracking_url(self):
        if self.tracking_code:
            return f"https://portal.packzy.com/tracking/{self.tracking_code}"
        return None

    def get_steadfast_cod_amount(self):
        return float(self.get_total()) if self.payment_method == 'cash_on_delivery' else 0.0

    # Order items accessor
    def get_order_items(self):
        return self.order_items.all()

    @classmethod
    def get_for_user(cls, request):
        """Unified order retrieval method"""
        if not request.session.session_key:
            request.session.create()

        return cls.objects.filter(
            models.Q(user=request.user) |
            models.Q(session_key=request.session.session_key),
            ordered=False
        ).prefetch_related('order_items').first()
class Address(models.Model):
    user = models.ForeignKey('core.User', on_delete=models.CASCADE,null=True,blank=True )
    full_name = models.CharField(max_length=255, blank= True, null= True)
    street_address = models.CharField(max_length=100, blank=True, null=True)
    apartment_address = models.CharField(max_length=100, blank=True, null=True)
    zip = models.CharField(max_length=100, blank=True, null=True)
    address_type = models.CharField(max_length=1, choices=ADDRESS_CHOICES)
    default = models.BooleanField(default=False)
    country = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=50, blank= True, null= True)
    thana = models.CharField(max_length=100,blank =True , null= True )
    def __str__(self):
        return f"{self.street_address}, {self.apartment_address}, {self.country}, {self.thana}"

    class Meta:
        verbose_name_plural = 'Addresses'


class Payment(models.Model):
    stripe_charge_id = models.CharField(max_length=50)
    user = models.ForeignKey('core.User',
                             on_delete=models.SET_NULL, blank=True, null=True)
    amount = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('fixed', 'Fixed Amount (Taka)'),
        ('percentage', 'Percentage (%)'),
    ]

    code = models.CharField(max_length=15, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='fixed')
    expiration_date = models.DateTimeField()
    active = models.BooleanField(default=True)

    def is_valid(self):
        """Check if the coupon is valid."""
        return self.active and self.expiration_date > timezone.now()

    def __str__(self):
        return self.code

class Refund(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    reason = models.TextField()
    accepted = models.BooleanField(default=False)
    email = models.EmailField()

    def __str__(self):
        return f"{self.pk}"


def userprofile_receiver(sender, instance, created, *args, **kwargs):
    if created:
        userprofile = UserProfile.objects.create(user=instance)


post_save.connect(userprofile_receiver, sender=settings.AUTH_USER_MODEL)


# NEW WORKS [SLIDER MODEL]

class Slider(models.Model):
    title = models.CharField(max_length=100,blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='slider_images/')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title if self.title else "Miabaaba Slider"


#career
class JobApplication(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    portfolio_url = models.URLField(blank=True, null=True)
    cover_letter = models.TextField()
    resume = models.FileField(upload_to='resumes/')
    applied_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

class Vacancy(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=100)
    posted_date = models.DateField(auto_now_add=True)
    application_deadline = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class Client(models.Model):
    name = models.CharField(max_length=255)