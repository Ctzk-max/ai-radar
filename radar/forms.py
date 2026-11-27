from django import forms

from .models import Event, Observation, Preferences, Source
from .network import FetchError, public_url


SOURCE_FIELDS = ("name", "url", "kind", "trust", "category", "platform", "weight", "interval",
                 "keywords", "follow", "enabled", "bridge_url", "selector", "page_title")
SOURCE_LABELS = dict(
    name="来源名称", url="来源链接", kind="采集方式", trust="来源属性", category="优先分类", platform="平台",
    weight="优先级 0–100", interval="刷新间隔（分钟）", keywords="关键词", follow="重点关注",
    enabled="启用定时采集", bridge_url="获授权的公开 RSS 镜像", selector="网页内容 CSS 选择器", page_title="网页跟踪标题",
)


def clean_url(value, *, source=False):
    try:
        return public_url(value, source=source)
    except FetchError as error:
        raise forms.ValidationError(str(error)) from None


class SourceForm(forms.ModelForm):
    url = forms.CharField(max_length=1200, label="来源链接", widget=forms.URLInput(attrs={"placeholder": "https://…"}))
    name = forms.CharField(max_length=110, label="来源名称", required=False)
    bridge_url = forms.CharField(max_length=1200, label="获授权的公开 RSS 镜像", required=False, widget=forms.URLInput)
    weight = forms.IntegerField(min_value=0, max_value=100, label="优先级 0–100")
    interval = forms.IntegerField(min_value=15, max_value=10080, label="刷新间隔（分钟）")

    class Meta:
        model = Source
        fields = SOURCE_FIELDS
        labels = SOURCE_LABELS
        help_texts = {"keywords": "用逗号分隔。未指定分类时，来源关键词同时用于筛选。"}

    def clean_url(self):
        return clean_url(self.cleaned_data["url"], source=True)

    def clean_bridge_url(self):
        value = self.cleaned_data["bridge_url"]
        return clean_url(value, source=True) if value else ""

    def clean(self):
        from urllib.parse import urlsplit
        values = super().clean()
        url = values.get("url", "")
        if url and not values.get("name"):
            values["name"] = urlsplit(url).hostname[:110]
        return values


class TestSourceForm(forms.Form):
    url = forms.CharField(max_length=1200, label="来源链接", widget=forms.URLInput)
    kind = forms.ChoiceField(choices=Source.Kind.choices, label="采集方式", initial=Source.Kind.AUTO)
    bridge_url = forms.CharField(max_length=1200, label="获授权的公开 RSS 镜像", required=False, widget=forms.URLInput)
    selector = forms.CharField(max_length=170, required=False, label="网页内容 CSS 选择器")

    clean_url = SourceForm.clean_url
    clean_bridge_url = SourceForm.clean_bridge_url


class PreferenceForm(forms.ModelForm):
    blocked_categories = forms.MultipleChoiceField(label="屏蔽类别", choices=Event._meta.get_field("category").choices,
                                                   widget=forms.CheckboxSelectMultiple, required=False)
    dark = forms.ChoiceField(label="配色", choices=[("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")])

    class Meta:
        model = Preferences
        fields = ("interests", "blocked_platforms", "blocked_categories", "hide_read", "dark")
        labels = {"interests": "兴趣关键词", "blocked_platforms": "屏蔽平台", "hide_read": "精选中隐藏已读"}
        help_texts = {"interests": "用逗号分隔。关键词和重点关注的来源会提高精选排序。",
                      "blocked_platforms": "用逗号分隔，按信息卡上的平台名称匹配。"}


class ClaimForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ("claim", "claim_note")
        labels = {"claim": "领取状态", "claim_note": "个人备注"}
        widgets = {"claim_note": forms.Textarea(attrs={"rows": 3})}


class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = ("model", "dimension", "metric", "value", "unit", "method", "trust", "url", "observed_on")
        labels = {"model": "模型与版本", "dimension": "能力维度", "metric": "指标", "value": "记录值", "unit": "单位",
                  "method": "指标含义与测试条件", "trust": "证据类型", "url": "证据链接", "observed_on": "观察日期"}
        widgets = {"observed_on": forms.DateInput(attrs={"type": "date"}), "method": forms.Textarea(attrs={"rows": 3})}

    def clean_url(self):
        return clean_url(self.cleaned_data["url"])
