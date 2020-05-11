# Generated by Django 3.0.5 on 2020-05-10 11:29

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("dns_grpc", "0002_auto_20200510_1013"),
    ]

    operations = [
        migrations.CreateModel(
            name="DSRecord",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, primary_key=True, serialize=False
                    ),
                ),
                (
                    "record_name",
                    models.CharField(
                        default="@",
                        max_length=255,
                        verbose_name="Record name (@ for zone root)",
                    ),
                ),
                (
                    "ttl",
                    models.PositiveIntegerField(verbose_name="Time to Live (seconds)"),
                ),
                (
                    "key_tag",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MaxValueValidator(65535)]
                    ),
                ),
                (
                    "algorithm",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (3, "DSA/SHA1 (3) INSECURE"),
                            (5, "RSA/SHA-1 (5) INSECURE"),
                            (6, "DSA-NSEC3-SHA1 (6) INSECURE"),
                            (7, "RSASHA1-NSEC3-SHA1 (7) INSECURE"),
                            (8, "RSA/SHA-256 (8)"),
                            (10, "RSA/SHA-512 (10)"),
                            (12, "GOST R 34.10-2001 (12)"),
                            (13, "ECDSA Curve P-256 with SHA-256 (13)"),
                            (14, "ECDSA Curve P-384 with SHA-384 (14)"),
                            (15, "Ed25519 (15)"),
                            (16, "Ed448 (16)"),
                        ]
                    ),
                ),
                (
                    "digest_type",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "SHA-1 (1) INSECURE"),
                            (2, "SHA-256 (2)"),
                            (3, "GOST R 34.11-94 (3)"),
                            (4, "SHA-384 (4)"),
                        ]
                    ),
                ),
                ("digest", models.TextField()),
                (
                    "zone",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="dns_grpc.DNSZone",
                    ),
                ),
            ],
            options={"verbose_name": "DS record", "verbose_name_plural": "DS records",},
        ),
    ]
