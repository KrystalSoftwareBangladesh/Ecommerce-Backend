# blog_api/views/v1/blog_post.py
from django.shortcuts import get_object_or_404

from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes,
)

from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import (
    FormParser, JSONParser, MultiPartParser,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import (
    CustomPermissionAccessMixin,
    ModelPermissionAccess,
    PublicReadPermissionMixin,
)

from blog_api.filters import BlogPostFilter
from blog_api.models import BlogPost, BlogPostStatus
from blog_api.serializers import (
    BlogPostCreateSerializer,
    BlogPostDetailSerializer,
    BlogPostListSerializer,
    BlogPostUpdateSerializer,
)
from blog_api.services import (
    delete_blog_post,
    publish_blog_post,
    unpublish_blog_post,
)


BLOG_POST_LOOKUP_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Blog post ID or slug",
)


@extend_schema(tags=["Blog"])
@extend_schema_view(
    retrieve=extend_schema(parameters=[BLOG_POST_LOOKUP_PARAMETER]),
    update=extend_schema(parameters=[BLOG_POST_LOOKUP_PARAMETER]),
    partial_update=extend_schema(parameters=[BLOG_POST_LOOKUP_PARAMETER]),
    destroy=extend_schema(parameters=[BLOG_POST_LOOKUP_PARAMETER]),
)
class BlogPostViewSet(
    CustomPermissionAccessMixin,
    PublicReadPermissionMixin,
    viewsets.ModelViewSet,
):
    """
    Blog posts.

    Reading is public and shows published, non-deleted posts only.
    Writing is driven by Django model permissions, and publishing has its
    own pair of permissions, so an editor can be allowed to write posts
    without being allowed to put them live.
    """
    permission_classes = [IsAuthenticated, ModelPermissionAccess]
    custom_permissions = {
        "publish": "publish_blog_post",
        "unpublish": "unpublish_blog_post",
    }
    parser_classes = [
        JSONParser,
        MultiPartParser,
        FormParser,
    ]
    queryset = BlogPost.objects.filter(deleted_at__isnull=True)
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = BlogPostFilter
    search_fields = [
        'title',
        'content',
        'seo_title',
        'seo_description',
        'seo_focus_keyword',
    ]
    ordering_fields = [
        'published_at',
        'created_at',
        'updated_at',
        'title',
        'id',
    ]
    ordering = ['-published_at', '-created_at']
    lookup_field = "id"
    lookup_url_kwarg = "id"
    lookup_value_regex = r"[^/]+"

    def _includes_unpublished(self):
        """
        Whether the current request may see posts that are not publicly
        visible.

        Only `list` and `retrieve` are open to the public, and there the
        gate is `view_blogpost`: without it a caller sees the published
        blog and nothing else. Every other action is already behind its
        own model permission, so it works on the full set — a user
        allowed to publish must be able to reach the draft.
        """
        if getattr(self, 'action', None) not in self.public_actions:
            return True

        request = getattr(self, 'request', None)
        user = getattr(request, 'user', None)

        return bool(
            user
            and user.is_authenticated
            and user.has_perm('blog_api.view_blogpost')
        )

    def get_queryset(self):
        queryset = BlogPost.objects.filter(deleted_at__isnull=True)

        if not self._includes_unpublished():
            queryset = queryset.filter(
                is_active=True,
                status=BlogPostStatus.PUBLISHED,
            )

        queryset = queryset.prefetch_related('categories', 'tags')

        if self.action == 'list':
            return queryset.select_related('author')

        return queryset.select_related(
            'author',
            'created_by',
            'updated_by',
        )

    def get_object(self):
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        queryset = self.filter_queryset(self.get_queryset())

        if lookup_value.isdigit():
            obj = get_object_or_404(queryset, pk=int(lookup_value))
        else:
            obj = get_object_or_404(queryset, slug=lookup_value)

        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return BlogPostListSerializer

        if self.action == 'create':
            return BlogPostCreateSerializer

        if self.action in ['update', 'partial_update']:
            return BlogPostUpdateSerializer

        return BlogPostDetailSerializer

    def _detail_response(self, post, response_status):
        return Response(
            BlogPostDetailSerializer(
                post,
                context=self.get_serializer_context(),
            ).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save()

        return self._detail_response(post, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        post = self.get_object()

        serializer = self.get_serializer(
            post,
            data=request.data,
            partial=kwargs.pop('partial', False),
        )
        serializer.is_valid(raise_exception=True)
        post = serializer.save()

        return self._detail_response(post, status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        post = self.get_object()

        delete_blog_post(post=post, user=request.user)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["Blog"],
        parameters=[BLOG_POST_LOOKUP_PARAMETER],
        request=None,
        responses={200: BlogPostDetailSerializer},
        description="Publish a draft post and stamp its publication time.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="publish",
        filter_backends=[],
        pagination_class=None,
    )
    def publish(self, request, id=None):
        post = self.get_object()

        published = publish_blog_post(post=post, user=request.user)

        return self._detail_response(published, status.HTTP_200_OK)

    @extend_schema(
        tags=["Blog"],
        parameters=[BLOG_POST_LOOKUP_PARAMETER],
        request=None,
        responses={200: BlogPostDetailSerializer},
        description=(
            "Return a published post to draft and clear its publication "
            "time. The post stops being publicly readable."
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="unpublish",
        filter_backends=[],
        pagination_class=None,
    )
    def unpublish(self, request, id=None):
        post = self.get_object()

        drafted = unpublish_blog_post(post=post, user=request.user)

        return self._detail_response(drafted, status.HTTP_200_OK)
