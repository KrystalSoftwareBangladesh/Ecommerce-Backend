# review_api/serialziers/review.py
from rest_framework import serializers

from django.db.models import Avg, Count
from django.db import IntegrityError

from review_api.models import Review


class UserMinimalSerializer(serializers.Serializer):
    """Minimal user info for review display."""
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    # Add avatar/profile_pic if you have it
    # avatar = serializers.ImageField(read_only=True, source='profile.avatar')


class ReviewListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing reviews on product pages.
    Includes minimal user info and product context.
    """
    user = UserMinimalSerializer(source='created_by', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id',
            'user',
            'rating',
            'title',
            'body',
            'is_verified_purchase',
            'status',
            'status_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'status',
            'is_verified_purchase',
        ]


class ReviewDetailSerializer(serializers.ModelSerializer):
    """
    Full detail serializer for individual review view.
    """
    user = UserMinimalSerializer(source='created_by', read_only=True)
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    approved_by_user = UserMinimalSerializer(
        source='approved_by', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id',
            'user',
            'product_id',
            'product_name',
            'rating',
            'title',
            'body',
            'is_verified_purchase',
            'status',
            'status_display',
            'approved_at',
            'approved_by_user',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'product_id',
            'product_name',
            'status',
            'approved_at',
            'approved_by_user',
            'is_verified_purchase',
            'created_at',
            'updated_at',
        ]


class ReviewCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating reviews.
    Handles validation and user injection.
    """

    class Meta:
        model = Review
        fields = [
            'product',
            'rating',
            'title',
            'body',
        ]

    def validate_rating(self, value):
        """Ensure rating is between 1 and 5."""
        if value < 1 or value > 5:
            raise serializers.ValidationError(
                "Rating must be between 1 and 5.")
        return value

    def validate_title(self, value):
        """Ensure title is not empty or too short."""
        if len(value.strip()) < 3:
            raise serializers.ValidationError(
                "Title must be at least 3 characters long.")
        return value

    def validate_body(self, value):
        """Ensure body has meaningful content."""
        if len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Review body must be at least 10 characters long.")
        return value

    def create(self, validated_data):
        """
        Create a new review.
        Injects the current user as created_by.
        """
        user = self.context['request'].user
        validated_data['created_by'] = user

        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({
                'non_field_errors': [
                    'You have already reviewed this product. You can edit your existing review instead.'    # noqa
                ]
            })

    def update(self, instance, validated_data):
        """
        Update an existing review.
        Only allows editing own reviews (enforced in view).
        """
        return super().update(instance, validated_data)


class ProductReviewStatsSerializer(serializers.Serializer):
    """
    Serializer for product review statistics.
    Used to display average rating and review count on product pages.
    """
    average_rating = serializers.FloatField(read_only=True)
    total_reviews = serializers.IntegerField(read_only=True)
    rating_distribution = serializers.DictField(read_only=True)

    def to_representation(self, instance):
        """
        Calculate review statistics for a product.
        instance should be a Product object.
        """
        reviews = instance.reviews.filter(
            is_active=True,
            status=2  # ModerationStatus.APPROVED
        )

        # Calculate average and count
        stats = reviews.aggregate(
            avg_rating=Avg('rating'),
            total=Count('id')
        )

        # Calculate rating distribution (how many 1-star, 2-star, etc.)
        distribution = {}
        for rating in range(1, 6):
            count = reviews.filter(rating=rating).count()
            distribution[str(rating)] = count

        return {
            'average_rating': round(stats['avg_rating'] or 0, 1),
            'total_reviews': stats['total'],
            'rating_distribution': distribution
        }
