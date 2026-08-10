# user_api/serializers/user.py
from rest_framework import serializers

from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password

from drf_spectacular.utils import extend_schema_field

from user_api.models import User
from .group import GroupSummarySerializer


class GroupPKRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        return {
            'id': value.id,
            'name': value.name,
        }


class UserProfileSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        # required=True,
        required=False,
        validators=[validate_password],
    )
    confirm_password = serializers.CharField(
        write_only=True,
        # required=True,
        required=False,
    )

    groups = GroupPKRelatedField(
        queryset=Group.objects.all(),
        many=True,
        required=False,
    )
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'first_name', 'middle_name', 'last_name',
            'email', 'username', 'password', 'confirm_password', 'groups',
            'permissions', 'is_superuser', 'role',
        ]
        read_only_fields = ['id', 'is_superuser']
        write_only = ['password', 'confirm_password']

    def __init__(self, *args, **kwargs):
        """Dynamically modify fields based on request method."""
        super().__init__(*args, **kwargs)
        request = self.context.get('request')   # noqa

    def to_representation(self, instance):
        """
            Modify response to always return full_name instead of separate
            name fields. Also rename is_superuser to is_superadmin.
        """
        data = super().to_representation(instance)

        data.pop('first_name', None)
        data.pop('middle_name', None)
        data.pop('last_name', None)

        # Rename is_superuser to is_superadmin
        if 'is_superuser' in data:
            data['is_superadmin'] = data.pop('is_superuser')

        return data

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj) -> list[str]:
        return sorted(obj.get_all_permissions())

    def validate(self, data):
        return data

    def _create_validation(self, data):
        if not data.get('username', None):
            raise serializers.ValidationError({"username": "Username required"})    # noqa

        if not data.get('email', None):
            raise serializers.ValidationError({"email": "Email required"})

        password = data.get('password', None)
        confirm_password = data.get('confirm_password', None)

        # if not password or not confirm_password:
        #     raise serializers.ValidationError({
        #         "password": "Password and Confirm Password both required",
        #     })

        if password != confirm_password:
            raise serializers.ValidationError({
                "password": "Password do not match"
            })

    def create(self, validated_data):
        """
            Create a new user and assign a role.
        """
        self._create_validation(data=validated_data)

        validated_data.pop('confirm_password', None)
        groups = validated_data.pop('groups', [])

        password = validated_data.pop('password', None)
        # user = User.objects.create_user(**validated_data)
        user = User(**validated_data)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save()
        user.groups.set(groups)

        return user

    def update(self, instance, validated_data):
        validated_data.pop('password', None)
        validated_data.pop('confirm_password', None)
        groups = validated_data.pop('groups', None)

        user = super().update(instance, validated_data)
        if groups is not None:
            user.groups.set(groups)
        return user


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
    )

    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "username",
            "password",
            "confirm_password",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError({
                "password": "Password do not match."
            })

        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")

        password = validated_data.pop("password")

        user = User(**validated_data, role="STAFF",)
        user.set_password(password)
        user.save()

        return user


class UserUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "username",
        ]
        read_only_fields = ["id"]


class UserListSerializer(serializers.ModelSerializer):
    groups = GroupSummarySerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "username",
            "groups",
        ]


class UserDetailSerializer(serializers.ModelSerializer):
    groups = GroupSummarySerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "username",
            "groups",
            "is_superuser",
        ]
        read_only_fields = [
            "id",
            "is_superuser",
        ]

    @extend_schema_field(
        serializers.ListField(
            child=serializers.CharField()
        )
    )
    def get_permissions(self, obj) -> list[str]:
        return sorted(obj.get_all_permissions())

    def to_representation(self, instance):
        data = super().to_representation(instance)

        data.pop("first_name", None)
        data.pop("middle_name", None)
        data.pop("last_name", None)

        data["is_superadmin"] = data.pop("is_superuser")

        return data


class ChangeUserUsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username"]

    def validate_username(self, value):
        value = value.strip().lower()

        if User.objects.filter(
            username__iexact=value
        ).exclude(
            pk=self.instance.pk
        ).exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )

        return value

    def update(self, instance, validated_data):
        instance.username = validated_data["username"]
        instance.save(update_fields=["username", "updated_at"])

        return instance
# class ChangeUserEmailSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User
#         fields = ["email"]

#     def validate_email(self, value):
#         value = value.strip().lower()

#         if User.objects.filter(
#             email__iexact=value
#         ).exclude(
#             pk=self.instance.pk
#         ).exists():
#             raise serializers.ValidationError(
#                 "A user with this email already exists."
#             )

#         return value

    # def update(self, instance, validated_data):
    #     instance.email = validated_data["email"]
    #     instance.save(update_fields=["email", "updated_at"])

    #     return instance


class UserExistenceCheckSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False)

    def validate(self, data):
        if not data.get("email") and not data.get("username"):
            raise serializers.ValidationError(
                "Either email or username must be provided."
            )
        return data


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'username']
