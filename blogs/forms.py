from __future__ import annotations

from typing import Any, cast

from django import forms
from django.utils.text import slugify

from .models import Blog


def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        existing = str(field.widget.attrs.get("class", "")).strip()
        merged = f"{existing} form-input".strip()
        field.widget.attrs["class"] = merged


class BlogForm(forms.ModelForm):
    class Meta:
        model = Blog
        fields = ("title", "slug", "excerpt", "body", "is_published")
        widgets: dict[str, forms.Widget] = cast(
            dict[str, forms.Widget],
            {
                "body": forms.Textarea(attrs={"rows": 10}),
            },
        )
        help_texts = {
            "slug": "Optional. Leave blank to auto-generate from title.",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)
        self.fields["slug"].required = False

    def clean_title(self) -> str:
        title = str(self.cleaned_data.get("title", "")).strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_slug(self) -> str:
        raw_slug = str(self.cleaned_data.get("slug", "")).strip()
        if not raw_slug:
            return ""

        normalized_slug = slugify(raw_slug)
        if not normalized_slug:
            raise forms.ValidationError("Slug must contain at least one letter or number.")

        duplicate_query = Blog.objects.filter(slug__iexact=normalized_slug)
        if self.instance.pk:
            duplicate_query = duplicate_query.exclude(pk=self.instance.pk)

        if duplicate_query.exists():
            raise forms.ValidationError("A blog with this slug already exists.")

        return normalized_slug

    def clean_excerpt(self) -> str:
        return str(self.cleaned_data.get("excerpt", "")).strip()

    def clean_body(self) -> str:
        body = str(self.cleaned_data.get("body", "")).strip()
        if not body:
            raise forms.ValidationError("Body is required.")
        return body

    def _generate_unique_slug(self, base_text: str) -> str:
        base_slug = slugify(base_text) or "blog"
        candidate = base_slug
        suffix = 2

        while Blog.objects.filter(slug__iexact=candidate).exclude(pk=self.instance.pk).exists():
            candidate = f"{base_slug}-{suffix}"
            suffix += 1

        return candidate

    def save(self, commit: bool = True) -> Blog:  # type: ignore[override]
        blog = super().save(commit=False)
        blog.title = blog.title.strip()
        blog.excerpt = blog.excerpt.strip()
        blog.body = blog.body.strip()

        if not blog.slug:
            blog.slug = self._generate_unique_slug(blog.title)

        if commit:
            blog.save()
        return blog
