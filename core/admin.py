from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .views import print_invoice
from django.shortcuts import redirect, reverse, render
from django.urls import path
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import timedelta
from .steadfast_service import SteadfastCourierService
from .models import (
    Item, OrderItem, Order, Payment, Coupon, Refund, Address,
    UserProfile, Slider, Category, ProductImage, Color, ItemVariant, Subcategory, JobApplication, Vacancy
)

def make_refund_accepted(modeladmin, request, queryset):
    queryset.update(refund_granted=True)

def make_refund_denied(modeladmin, request, queryset):
    queryset.update(refund_granted=False)

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'shipping_name', 'verified', 'consignment_id', 'tracking_code',
        'delivery_status', 'display_total_price', 'order_channel',
        'being_delivered', 'received', 'payment_method', 'call_count',
        'client', 'order_items_summary'
    ]

    list_filter = [
        'verified', 'being_delivered', 'received',
        'payment_method', 'order_channel', 'delivery_status'
    ]

    search_fields = ['user__username', 'ref_code', 'consignment_id', 'tracking_code']

    actions = [
        'increment_call_count',
        'mark_as_verified',
        'print_invoice_action',
        'send_to_steadfast',
        'check_steadfast_status'
    ]

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                'fields': ('user', 'session_key', 'ref_code', 'ordered', 'order_channel', 'delivery_charge')
            }),
            ('Shipping Information', {
                'fields': ('shipping_address', 'shipping_thana', 'shipping_country', 'shipping_zip')
            }),
            ('Billing Information', {
                'fields': ('billing_address', 'billing_thana', 'billing_country')
            }),
            ('Payment Information', {
                'fields': ('payment_method', 'transaction_id', 'bikash_nagad_number', 'phone_number')
            }),
            ('Order Status', {
                'fields': ('being_delivered', 'received', 'verified', 'call_count', 'verification_note')
            }),
        ]

        if obj and obj.payment_method in ['bikash', 'nagad']:
            fieldsets[3][1]['fields'].append('transaction_id')
            fieldsets[3][1]['fields'].append('bikash_nagad_number')

        # Add Steadfast section
        fieldsets.append(
            ('Steadfast Courier Integration', {
                'fields': (
                    'consignment_id',
                    'tracking_code',
                    'delivery_status',
                    'steadfast_data'
                )
            })
        )
        return fieldsets

    def send_to_steadfast(self, request, queryset):
        verified_orders = queryset.filter(verified=True, consignment_id__isnull=True)
        courier_service = SteadfastCourierService()
        success_count = 0

        for order in verified_orders:
            try:
                response = courier_service.create_order({
                    "invoice": order.get_invoice_id(),
                    "recipient_name": order.shipping_name,
                    "recipient_phone": order.phone_number,
                    "recipient_address": str(order.shipping_address),
                    "cod_amount": float(order.get_total()),
                    "note": "Verified order from admin"
                })

                if response.get('consignment'):
                    order.consignment_id = response['consignment']['consignment_id']
                    order.tracking_code = response['consignment']['tracking_code']
                    order.delivery_status = response['consignment']['status']
                    order.steadfast_data = response
                    order.save()
                    success_count += 1

            except Exception as e:
                self.message_user(request,
                                  f"Error processing order {order.id}: {str(e)}",
                                  level='error'
                                  )

        if success_count:
            self.message_user(request,
                              f"Successfully sent {success_count} orders to Steadfast Courier")

    send_to_steadfast.short_description = "Send verified orders to Steadfast"

    def check_steadfast_status(self, request, queryset):
        courier_service = SteadfastCourierService()
        updated = 0

        for order in queryset.filter(consignment_id__isnull=False):
            status = courier_service.get_delivery_status(
                order.consignment_id,
                'consignment_id'
            )
            if status.get('delivery_status'):
                order.delivery_status = status['delivery_status']
                order.save()
                updated += 1

        self.message_user(request, f"Updated status for {updated} orders")

    check_steadfast_status.short_description = "Refresh Steadfast statuses"

    def mark_as_verified(self, request, queryset):
        for order in queryset:
            order.verified = True
            order.verification_note = "Order verified after phone call."
            order.save()

        # Automatically send to Steadfast
        self.send_to_steadfast(request, queryset.filter(verified=True))

        self.message_user(request,
                          f"{queryset.count()} orders verified and sent to Steadfast")

    def display_total_price(self, obj):
        """Display the total price for the order."""
        total_price = obj.get_total()  # Call the get_total method from the Order model
        if not obj.verified:
            return format_html('<span style="color: red;">{}</span>', total_price)
        return total_price

    display_total_price.short_description = 'Total Price'

    def order_items_summary(self, obj):
        """Corrected implementation without super()"""
        items = obj.order_items.all()
        summary = []

        for item in items:
            summary.append(
                f"{item.quantity}x {item.item.title} "
                f"(Price: ৳{item.get_total_item_price()})"
            )

        if obj.tracking_code:
            summary.append(
                f"Tracking: {obj.tracking_code} "
                f"(Status: {obj.get_delivery_status_display()})"
            )

        return format_html("<br>".join(summary))

    order_items_summary.short_description = 'Items & Tracking'

    def client(self, obj):
        """Return the client name based on the order channel."""
        return "SteadFast" if obj.order_channel != 'In house' else obj.user.username  # Assuming user is linked to the order

    client.short_description = 'Client'

    def increment_call_count(self, request, queryset):
        for order in queryset:
            order.call_count += 1
            order.verification_note = f"Called {order.call_count} times."
            order.save()
            if order.call_count >= 3:
                order.delete()  # Automatically delete the order if called 3 times
                self.message_user(request, f"Order {order.id} has been deleted after 3 calls.")
            else:
                self.message_user(request, f"Order {order.id} call count incremented to {order.call_count}.")

    increment_call_count.short_description = "Increment call count for selected orders"

    def print_invoice_action(self, request, queryset):
        for order in queryset:
            # Redirect to the invoice view for each selected order
            return HttpResponseRedirect(reverse('core:print_invoice', args=[order.id]))

    print_invoice_action.short_description = "Print Invoice for selected orders"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('print-invoice/<int:order_id>/', self.admin_site.admin_view(self.print_invoice_action),
                 name='print_invoice'),
        ]
        return custom_urls + urls

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        if obj and obj.consignment_id:
            return readonly + ['consignment_id', 'tracking_code', 'steadfast_data']
        return readonly

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'full_name', 'street_address', 'apartment_address',
        'zip', 'address_type', 'default'
    ]
    list_filter = ['default', 'address_type']
    search_fields = ['user__username', 'full_name', 'street_address', 'apartment_address', 'zip']


# Inline admin for managing multiple ProductImages in Item
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3  # Default number of empty forms


# Inline admin for managing ItemVariants in Item
class ItemVariantInline(admin.TabularInline):
    model = ItemVariant
    extra = 1  # Default number of empty forms


# Custom filter for available colors in the Item model
class AvailableColorFilter(admin.SimpleListFilter):
    title = _('Available Color')
    parameter_name = 'available_color'

    def lookups(self, request, model_admin):
        return [(color.name, color.name) for color in Color.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(variants__color__name=self.value())
        return queryset

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'price', 'product_code', 'category',
        'label', 'get_available_colors', 'get_stock_info'
    ]
    list_filter = ['category', 'label', AvailableColorFilter]
    search_fields = ['title', 'category__name', 'product_code']
    inlines = [ProductImageInline, ItemVariantInline]

    def get_available_colors(self, obj):
        return ", ".join(obj.variants.values_list('color__name', flat=True).distinct())
    get_available_colors.short_description = _('Available Colors')

    def get_stock_info(self, obj):
        stock_info = []
        for variant in obj.variants.all():  # Assuming 'variants' is the related name for ItemVariant
            url = reverse('admin:stock-chart')  # No arguments needed
            stock_info.append(
                f'<a href="{url}">{variant.color.name if variant.color else "No Color"}</a>: {variant.quantity_in_stock}')
        return mark_safe(", ".join(stock_info))  # Join the stock info and mark as safe
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('stock-chart/', self.admin_site.admin_view(self.stock_chart_view), name='stock-chart'),
        ]
        return custom_urls + urls

    def stock_chart_view(self, request):
        items = Item.objects.all()
        item_names = [item.title for item in items]
        stock_levels = [sum(variant.quantity_in_stock for variant in item.variants.all()) for item in items]

        context = {
            'item_names': item_names,
            'stock_levels': stock_levels,
        }
        return render(request, 'stock_chart.html', context)
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['stock_chart_url'] = 'stock-chart/'  # Add the URL for the stock chart
        return super().changelist_view(request, extra_context=extra_context)
# Admin customization for Category model
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}


# Admin customization for Slider model
@admin.register(Slider)
class SliderAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    list_filter = ('is_active',)


# Admin customization for Color model
@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('name', 'hex_value')
    search_fields = ('name',)


# Registering remaining models
admin.site.register(Coupon)
admin.site.register(Refund)
admin.site.register(UserProfile)
admin.site.register(Subcategory)

@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone_number', 'applied_on')
    search_fields = ('full_name', 'email', 'phone_number')
    list_filter = ('applied_on',)
    ordering = ('-applied_on',)


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ('title', 'location', 'posted_date', 'application_deadline', 'is_active')
    list_filter = ('is_active', 'location')
    search_fields = ('title', 'description')
    date_hierarchy = 'posted_date'

class OrderDateFilter(admin.SimpleListFilter):
    title = 'Order Date'
    parameter_name = 'order_date'

    def lookups(self, request, model_admin):
        return (
            ('last_7_days', 'Last 7 Days'),
            ('last_30_days', 'Last 30 Days'),
            ('this_month', 'This Month'),
            ('last_month', 'Last Month'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'last_7_days':
            return queryset.filter(order__ordered_date__gte=timezone.now() - timedelta(days=7))
        if self.value() == 'last_30_days':
            return queryset.filter(order__ordered_date__gte=timezone.now() - timedelta(days=30))
        if self.value() == 'this_month':
            return queryset.filter(order__ordered_date__month=timezone.now().month, order__ordered_date__year=timezone.now().year)
        if self.value() == 'last_month':
            return queryset.filter(order__ordered_date__month=timezone.now().month - 1, order__ordered_date__year=timezone.now().year)
        return queryset

class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['get_item_name', 'get_price', 'quantity', 'get_total_price', 'get_client']
    list_filter = [OrderDateFilter]  # Add the custom date filter

    def get_item_name(self, obj):
        return obj.item.title  # Assuming item has a title attribute
    get_item_name.short_description = 'Item Name'

    def get_price(self, obj):
        return obj.item.price  # Assuming item has a price attribute
    get_price.short_description = 'Unit Price'

    def get_total_price(self, obj):
        return obj.get_total_item_price()  # Call the method to get total item price
    get_total_price.short_description = 'Total Price'

    def get_client(self, obj):
        # Logic to determine the client based on the order channel
        if obj.order and obj.order.order_channel != 'in_house':
            return "Steadfast"
        return "In House Client"  # Default client name for in-house orders
    get_client.short_description = 'Client'

admin.site.register(OrderItem, OrderItemAdmin)