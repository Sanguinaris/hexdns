# Generated by Django 2.2.18 on 2021-04-14 20:31

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('dns_grpc', '0009_auto_20210309_1508'),
    ]

    operations = [
        migrations.CreateModel(
            name='GitHubState',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.UUIDField(default=uuid.uuid4)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dns_grpc.Account')),
            ],
        ),
        migrations.CreateModel(
            name='GitHubInstallation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('installation_id', models.PositiveIntegerField()),
                ('access_token', models.TextField(blank=True, null=True)),
                ('access_token_expires_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='dns_grpc.Account')),
            ],
        ),
    ]