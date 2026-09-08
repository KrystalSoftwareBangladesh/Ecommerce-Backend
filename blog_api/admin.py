# blog_api/admin.py
from django.contrib import admin

from blog_api.models import BlogPost, BlogTag


@admin.register(BlogTag)
class BlogTagAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'legacy_id',
        'is_active',
        'created_at',
    )
    list_filter = (
        'is_active',
    )
    search_fields = (
        'name',
        'slug',
    )
    readonly_fields = (
        'slug',
        'created_by',
        'updated_by',
        'created_at',
        'updated_at',
        'deleted_at',
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user

        super().save_model(request, obj, form, change)


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'slug',
        'author',
        'status',
        'published_at',
        'is_active',
        'updated_at',
    )
    list_filter = (
        'status',
        'is_active',
        'author',
    )
    search_fields = (
        'title',
        'slug',
        'content',
        'seo_title',
        'seo_description',
        'seo_focus_keyword',
    )
    autocomplete_fields = (
        'tags',
    )
    filter_horizontal = (
        'categories',
    )
    list_select_related = ('author',)
    date_hierarchy = 'published_at'
    ordering = ('-published_at', '-created_at')
    fieldsets = (
        ('Content', {
            'fields': (
                'title',
                'slug',
                'content',
                'author',
            ),
        }),
        ('Publication', {
            'fields': (
                'status',
                'published_at',
            ),
            'description': 'Read-only. Publication state is changed '
                           'through the publish and unpublish endpoints '
                           'so the two stay consistent.',
        }),
        ('Featured image', {
            'fields': (
                'featured_image',
                'featured_image_alt_text',
            ),
        }),
        ('Taxonomy', {
            'fields': (
                'categories',
                'tags',
            ),
        }),
        ('SEO', {
            'fields': (
                'seo_title',
                'seo_description',
                'seo_focus_keyword',
                'seo_noindex',
                'seo_nofollow',
            ),
        }),
        ('Migration', {
            'fields': (
                'legacy_id',
            ),
            'classes': ('collapse',),
        }),
        ('Audit trail', {
            'fields': (
                'created_by',
                'updated_by',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
        ('Soft delete', {
            'fields': (
                'is_active',
                'deleted_at',
            ),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = (
        'slug',
        'status',
        'published_at',
        'created_by',
        'updated_by',
        'created_at',
        'updated_at',
        'deleted_at',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'categories',
            'tags',
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user

        super().save_model(request, obj, form, change)
