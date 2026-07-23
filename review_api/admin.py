# review_api/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import Review
from EcommerceBackend.core.models import ModerationStatus


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """
    Admin interface for product reviews with moderation workflow support.
    """

    # 1. List View Configuration
    list_display = (
        'id',
        'title_short',
        'product',
        'rating_stars',
        'status_badge',
        'is_verified_purchase',
        'created_by',
        'created_at',
        'is_active',
    )

    list_display_links = ('id', 'title_short')

    list_filter = (
        'status',
        'is_verified_purchase',
        'is_active',
        'rating',
        'created_at',
        'product',
    )

    search_fields = (
        'title',
        'body',
        'created_by__username',
        'created_by__email',
        'product__name',
    )

    list_select_related = ('product', 'created_by', 'approved_by')

    date_hierarchy = 'created_at'

    ordering = ('-created_at',)

    list_per_page = 25

    # 2. Fieldsets for Organized Detail View
    fieldsets = (
        ('Review Content', {
            'fields': ('product', 'rating', 'title', 'body')
        }),
        ('Purchase Verification', {
            'fields': ('is_verified_purchase',),
            'description': 'Mark as verified only if the user actually purchased this product.' # noqa
        }),
        ('Moderation', {
            'fields': ('status', 'approved_at', 'approved_by'),
        }),
        ('Audit Trail (Read-Only)', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
        ('Soft Delete', {
            'fields': ('is_active', 'deleted_at'),
            'classes': ('collapse',),
        }),
    )

    # 3. Read-Only Fields (Protect Audit Trail)
    readonly_fields = (
        'created_by',
        'updated_by',
        'created_at',
        'updated_at',
        'approved_at',
        'approved_by',
        'deleted_at',
    )

    # 4. Custom Admin Actions (Bulk Moderation)
    actions = [
        'mark_as_approved',
        'mark_as_rejected',
        'reset_to_pending',
        'soft_delete_selected',
        'restore_selected',
    ]

    # ------------------------------------------------------------------
    # Custom Display Methods
    # ------------------------------------------------------------------

    @admin.display(description='Title', ordering='title')
    def title_short(self, obj):
        """Truncate long titles for list view."""
        if len(obj.title) > 50:
            return f"{obj.title[:47]}..."
        return obj.title

    @admin.display(description='Rating', ordering='rating')
    def rating_stars(self, obj):
        """Display rating as visual stars."""
        full_stars = '★' * obj.rating
        empty_stars = '☆' * (5 - obj.rating)
        color = {
            5: '#28a745',  # Green
            4: '#5cb85c',  # Light green
            3: '#f0ad4e',  # Orange
            2: '#ff9800',  # Dark orange
            1: '#d9534f',  # Red
        }.get(obj.rating, '#999')

        return format_html(
            '<span style="color: {}; font-size: 14px;">{}{}</span> ({})',
            color,
            full_stars,
            empty_stars,
            obj.rating
        )

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            ModerationStatus.PENDING: ('#f0ad4e', 'Pending'),
            ModerationStatus.APPROVED: ('#28a745', 'Approved'),
            ModerationStatus.REJECTED: ('#d9534f', 'Rejected'),
        }
        color, label = colors.get(obj.status, ('#999', 'Unknown'))

        return format_html(
            '<span style="background: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">'
            '{}</span>',
            color,
            label
        )

    # ------------------------------------------------------------------
    # Custom Action Methods
    # ------------------------------------------------------------------

    @admin.action(description='✅ Approve selected reviews')
    def mark_as_approved(self, request, queryset):
        count = 0
        for review in queryset:
            review.approve(request.user)
            count += 1
        self.message_user(request, f'{count} review(s) approved successfully.')

    @admin.action(description='❌ Reject selected reviews')
    def mark_as_rejected(self, request, queryset):
        count = 0
        for review in queryset:
            review.reject()
            count += 1
        self.message_user(request, f'{count} review(s) rejected.')

    @admin.action(description='⏳ Reset selected reviews to pending')
    def reset_to_pending(self, request, queryset):
        count = queryset.update(
            status=ModerationStatus.PENDING,
            approved_at=None,
            approved_by=None
        )
        self.message_user(request, f'{count} review(s) reset to pending.')

    @admin.action(description='🗑️ Soft delete selected reviews')
    def soft_delete_selected(self, request, queryset):
        count = 0
        for review in queryset:
            review.soft_delete()
            count += 1
        self.message_user(request, f'{count} review(s) soft deleted.')

    @admin.action(description='♻️ Restore soft-deleted reviews')
    def restore_selected(self, request, queryset):
        count = queryset.update(
            is_active=True,
            deleted_at=None
        )
        self.message_user(request, f'{count} review(s) restored.')

    # ------------------------------------------------------------------
    # Queryset & Permissions
    # ------------------------------------------------------------------

    def get_queryset(self, request):
        """
        Include soft-deleted reviews in admin so staff can restore them.
        (Default manager might filter them out if you customize it later.)
        """
        return super().get_queryset(request)

    def save_model(self, request, obj, form, change):
        """Auto-populate audit fields on save."""
        if not change:
            # Creating new object
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
