from rest_framework import serializers

from django.contrib.auth.models import Group, Permission
from user_api.models import User

from user_api.serializers import PermissionSerializer


class GroupSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        many=True, write_only=True,
        required=False,
    )

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permission_ids']

    def to_internal_value(self, data):
        return super().to_internal_value(data)

    def validate_name(self, value):
        """Ensure role name is unique unless updating."""
        request = self.context.get('request')

        if request and request.method in ['PUT', 'PATCH']:
            role_id = self.instance.id if self.instance else None
            if Group.objects.exclude(id=role_id).filter(name=value).exists():
                raise serializers.ValidationError(
                    "This role name already exists."
                )
        else:
            if Group.objects.filter(name=value).exists():
                raise serializers.ValidationError("This role already exists.")
        return value

    def create(self, validated_data):
        permissions = validated_data.pop('permission_ids', [])
        group = Group.objects.create(**validated_data)
        group.permissions.set(permissions)

        return group

    def update(self, instance, validated_data):
        permissions = validated_data.pop('permission_ids', None)
        instance.name = validated_data.get('name', instance.name)
        instance.save()

        if permissions is not None:
            instance.permissions.set(permissions)

        return instance


class AssignGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'groups']

    def update(self, instance, validated_data):
        """Assign the specified roles to the user."""
        groups = validated_data.pop('groups', [])
        instance.groups.set(groups)

        return instance
