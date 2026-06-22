"""
Django admin configuration for standards_parser application.
"""

from django.contrib import admin
from .models import ParsedStandard, ParsingLog


@admin.register(ParsedStandard)
class ParsedStandardAdmin(admin.ModelAdmin):
    """Admin interface for ParsedStandard model."""
    list_display = ('standard_number', 'title', 'classification_number', 'status', 'parsed_at')
    list_filter = ('status', 'file_type', 'parsed_at')
    search_fields = ('standard_number', 'title', 'classification_number')
    readonly_fields = ('parsed_at', 'updated_at')
    fieldsets = (
        ('File Information', {
            'fields': ('source_file', 'file_type')
        }),
        ('Extracted Data', {
            'fields': ('standard_number', 'classification_number', 'title', 'content')
        }),
        ('Status', {
            'fields': ('status', 'error_message')
        }),
        ('Timestamps', {
            'fields': ('parsed_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ParsingLog)
class ParsingLogAdmin(admin.ModelAdmin):
    """Admin interface for ParsingLog model."""
    list_display = ('task_id', 'log_type', 'parsed_standard', 'created_at')
    list_filter = ('log_type', 'created_at')
    search_fields = ('task_id', 'message')
    readonly_fields = ('created_at', 'task_id')
    ordering = ('-created_at',)
