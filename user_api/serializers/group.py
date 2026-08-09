from rest_framework import serializers

from django.contrib.auth.models import Group, Permission
# from user_api.models import User

from .permission import PermissionSerializer


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


class GroupSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = [
            "id",
            "name",
        ]


class AssignGroupSerializer(serializers.Serializer):
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source='role',
    )

    def validate(self, attrs):
        user = self.instance
        role = attrs['role']

        if user.groups.filter(pk=role.pk).exists():
            raise serializers.ValidationError({
                'role_id': 'This role is already assigned to the user.'
            })

        return attrs

    def update(self, instance, validated_data):
        role = validated_data['role']

        instance.groups.add(role)

        return instance


class RemoveGroupSerializer(serializers.Serializer):
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source="role",
    )

    def validate(self, attrs):
        user = self.instance
        role = attrs["role"]

        if not user.groups.filter(pk=role.pk).exists():
            raise serializers.ValidationError({
                "role_id": "This role is not assigned to the user."
            })

        return attrs

    def update(self, instance, validated_data):
        instance.groups.remove(validated_data["role"])
        return instance
