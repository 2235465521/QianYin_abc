"""
Django ORM Models for standards_parser application.
Defines database table structures for standard document parsing and storage.
"""

from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone


class StandardDocument(models.Model):
    """
    Model for storing standard documents with comprehensive metadata.
    Manages the entire lifecycle of document processing from upload to parsing.
    """
    
    # Status choices
    STATUS_CHOICES = [
        ('pending', '待解析'),
        ('processing', '处理中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]
    
    # Standard identification
    standard_code = models.CharField(
        max_length=50,
        verbose_name='标准代号与顺序号',
        help_text='例如：GB/T 1.1',
        db_index=True
    )
    year_code = models.CharField(
        max_length=4,
        verbose_name='年代号',
        help_text='例如：2020'
    )
    
    # Names
    cn_name = models.CharField(
        max_length=500,
        verbose_name='中文名称',
        db_index=True
    )
    en_name = models.CharField(
        max_length=500,
        verbose_name='英文名称',
        blank=True,
        null=True
    )
    
    # Classification
    ics_code = models.CharField(
        max_length=50,
        verbose_name='ICS 分类号',
        help_text='国际标准分类号',
        blank=True,
        null=True
    )
    ccs_code = models.CharField(
        max_length=50,
        verbose_name='CCS 分类号',
        help_text='中国标准分类号',
        blank=True,
        null=True
    )
    
    # Important dates
    publish_date = models.DateField(
        verbose_name='发布日期',
        help_text='标准发布的日期'
    )
    implement_date = models.DateField(
        verbose_name='实施日期',
        help_text='标准开始实施的日期'
    )
    
    # Related standards
    replace_standard = models.CharField(
        max_length=200,
        verbose_name='代替标准号',
        help_text='该标准代替的先前标准',
        blank=True,
        null=True
    )
    
    # Revision changes (compared to previous version)
    revision_changes = models.JSONField(
        verbose_name='修订变化条目',
        blank=True,
        null=True,
        help_text='与上版标准相比的修订内容列表，格式：[{"index":"a","type":"增加","content":"..."}]'
    )
    extraction_source = models.CharField(
        max_length=20,
        verbose_name='提取来源',
        blank=True,
        null=True,
        help_text='修订条目的提取方式：regex / llm / regex_fallback / failed'
    )
    
    # File storage
    source_file = models.FileField(
        upload_to='standards/%Y/%m/%d/',
        verbose_name='原文件存储路径',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'docx', 'doc'])],
        help_text='上传的原始文件（PDF 或 Word 格式）'
    )
    
    # Processing status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='解析状态',
        db_index=True
    )
    
    # Error tracking
    error_reason = models.TextField(
        verbose_name='失败原因备注',
        blank=True,
        null=True,
        help_text='解析失败时记录详细原因'
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )
    
    # Traceability
    source_base_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        verbose_name='源库std_base主键ID'
    )
    
    class Meta:
        db_table = 'standard_documents'
        verbose_name = '国家标准文档'
        verbose_name_plural = '国家标准文档'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['standard_code']),
            models.Index(fields=['year_code']),
            models.Index(fields=['status']),
            models.Index(fields=['cn_name']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['source_base_id']),
        ]
    
    def __str__(self):
        return f"{self.standard_code}-{self.year_code} {self.cn_name}"
    
    @property
    def full_standard_number(self):
        """获取完整的标准号"""
        return f"{self.standard_code}-{self.year_code}"
    
    def get_status_display_cn(self):
        """获取中文状态显示"""
        return dict(self.STATUS_CHOICES).get(self.status, '未知')
