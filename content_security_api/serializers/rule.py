# content_security_api/serializers/rule.py
from rest_framework import serializers

from content_security_api.models import (
    DomainRule,
    HiddenContentRule,
    HtmlAttributeRule,
    HtmlTagRule,
    KeywordRule,
    ObfuscationRule,
    RedirectRule,
)


class BaseRuleListSerializer(serializers.ModelSerializer):
    """
    Lean shape shared by every rule list endpoint.
    """

    class Meta:
        fields = [
            'id',
            'category',
            'severity',
            'is_enabled',
            'is_active',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'is_active',
            'created_at',
        ]


class BaseRuleDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        fields = [
            'id',
            'category',
            'severity',
            'is_enabled',
            'description',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]
        read_only_fields = [
            'id',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]


class BaseRuleCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        fields = [
            'id',
            'category',
            'severity',
            'is_enabled',
            'description',
        ]
        read_only_fields = ['id']


class KeywordRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = KeywordRule
        fields = BaseRuleListSerializer.Meta.fields + [
            'keyword',
            'match_type',
        ]


class KeywordRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = KeywordRule
        fields = BaseRuleDetailSerializer.Meta.fields + [
            'keyword',
            'match_type',
        ]


class KeywordRuleCreateUpdateSerializer(BaseRuleCreateUpdateSerializer):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = KeywordRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + [
            'keyword',
            'match_type',
        ]

    def validate_keyword(self, value):
        keyword = (value or '').strip()

        if not keyword:
            raise serializers.ValidationError(
                'A keyword rule needs a keyword.'
            )

        return keyword


class DomainRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = DomainRule
        fields = BaseRuleListSerializer.Meta.fields + [
            'domain',
            'match_type',
        ]


class DomainRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = DomainRule
        fields = BaseRuleDetailSerializer.Meta.fields + [
            'domain',
            'match_type',
        ]


class DomainRuleCreateUpdateSerializer(BaseRuleCreateUpdateSerializer):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = DomainRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + [
            'domain',
            'match_type',
        ]

    def validate_domain(self, value):
        domain = (value or '').strip().strip('.').lower()

        if not domain:
            raise serializers.ValidationError(
                'A domain rule needs a domain.'
            )

        if '/' in domain or ' ' in domain:
            raise serializers.ValidationError(
                'Enter a bare host such as example.com, not a URL.'
            )

        return domain


class HtmlTagRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = HtmlTagRule
        fields = BaseRuleListSerializer.Meta.fields + ['tag']


class HtmlTagRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = HtmlTagRule
        fields = BaseRuleDetailSerializer.Meta.fields + ['tag']


class HtmlTagRuleCreateUpdateSerializer(BaseRuleCreateUpdateSerializer):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = HtmlTagRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + ['tag']

    def validate_tag(self, value):
        tag = (value or '').strip().lstrip('<').rstrip('>').lower()

        if not tag or not tag.isalnum():
            raise serializers.ValidationError(
                'Enter a plain tag name such as script.'
            )

        return tag


class HtmlAttributeRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = HtmlAttributeRule
        fields = BaseRuleListSerializer.Meta.fields + [
            'pattern',
            'pattern_type',
        ]


class HtmlAttributeRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = HtmlAttributeRule
        fields = BaseRuleDetailSerializer.Meta.fields + [
            'pattern',
            'pattern_type',
        ]


class HtmlAttributeRuleCreateUpdateSerializer(
    BaseRuleCreateUpdateSerializer
):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = HtmlAttributeRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + [
            'pattern',
            'pattern_type',
        ]

    def validate_pattern(self, value):
        pattern = (value or '').strip()

        if not pattern:
            raise serializers.ValidationError(
                'An attribute rule needs a pattern.'
            )

        return pattern


class RedirectRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = RedirectRule
        fields = BaseRuleListSerializer.Meta.fields + [
            'mechanism',
            'mechanism_type',
        ]


class RedirectRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = RedirectRule
        fields = BaseRuleDetailSerializer.Meta.fields + [
            'mechanism',
            'mechanism_type',
        ]


class RedirectRuleCreateUpdateSerializer(BaseRuleCreateUpdateSerializer):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = RedirectRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + [
            'mechanism',
            'mechanism_type',
        ]

    def validate_mechanism(self, value):
        mechanism = (value or '').strip()

        if not mechanism:
            raise serializers.ValidationError(
                'A redirect rule needs a mechanism.'
            )

        return mechanism


class HiddenContentRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = HiddenContentRule
        fields = BaseRuleListSerializer.Meta.fields + ['pattern']


class HiddenContentRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = HiddenContentRule
        fields = BaseRuleDetailSerializer.Meta.fields + ['pattern']


class HiddenContentRuleCreateUpdateSerializer(
    BaseRuleCreateUpdateSerializer
):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = HiddenContentRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + ['pattern']

    def validate_pattern(self, value):
        pattern = (value or '').strip()

        if ':' not in pattern:
            raise serializers.ValidationError(
                'Enter a CSS declaration such as display:none.'
            )

        return pattern


class ObfuscationRuleListSerializer(BaseRuleListSerializer):
    class Meta(BaseRuleListSerializer.Meta):
        model = ObfuscationRule
        fields = BaseRuleListSerializer.Meta.fields + ['indicator']


class ObfuscationRuleDetailSerializer(BaseRuleDetailSerializer):
    class Meta(BaseRuleDetailSerializer.Meta):
        model = ObfuscationRule
        fields = BaseRuleDetailSerializer.Meta.fields + [
            'indicator',
            'min_length',
        ]


class ObfuscationRuleCreateUpdateSerializer(BaseRuleCreateUpdateSerializer):
    class Meta(BaseRuleCreateUpdateSerializer.Meta):
        model = ObfuscationRule
        fields = BaseRuleCreateUpdateSerializer.Meta.fields + [
            'indicator',
            'min_length',
        ]


class DetectionRuleSummarySerializer(serializers.Serializer):
    """
    Rule counts per rule type, for the Detection Rules tab badges.
    """
    keyword_rules = serializers.IntegerField()
    domain_rules = serializers.IntegerField()
    hidden_content_rules = serializers.IntegerField()
    obfuscation_rules = serializers.IntegerField()
    redirect_rules = serializers.IntegerField()
    html_attribute_rules = serializers.IntegerField()
    html_tag_rules = serializers.IntegerField()
    total = serializers.IntegerField()
