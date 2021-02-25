import urllib.parse
import jwt
import secrets
import requests
import dnslib
import django_keycloak_auth.clients
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone

from .. import forms, grpc, models
from . import utils


@login_required
def zones(request):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zones = models.DNSZone.get_object_list(access_token)

    return render(request, "dns_grpc/fzone/zones.html", {
        "zones": user_zones,
        "account": request.user.account
    })


@login_required
def create_zone(request):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)

    if not models.DNSZone.has_class_scope(access_token, 'create'):
        raise PermissionDenied

    if request.method == "POST":
        form = forms.ZoneForm(request.POST)
        if form.is_valid():
            zone_root_txt = form.cleaned_data['zone_root'].lower()
            zone_error = utils.valid_zone(zone_root_txt)
            if zone_error:
                form.errors['zone_root'] = (zone_error,)
            else:
                status, extra = utils.log_usage(
                    request.user, extra=1, redirect_uri=settings.EXTERNAL_URL_BASE + reverse('zones'),
                    can_reject=True, off_session=False
                )
                if status == "error":
                    form.errors['__all__'] = (extra,)
                else:
                    zone_obj = models.DNSZone(
                        zone_root=zone_root_txt,
                        last_modified=timezone.now(),
                        user=request.user,
                        zsk_private=utils.get_priv_key_bytes()
                    )
                    zone_obj.save()
                    if status == "redirect":
                        return redirect(extra)
                    return redirect('edit_zone', zone_obj.id)
    else:
        form = forms.ZoneForm()

    return render(request, "dns_grpc/fzone/create_zone.html", {
        "form": form
    })


@login_required
def create_domains_zone(request):
    client_token = django_keycloak_auth.clients.get_access_token()
    referrer = request.META.get("HTTP_REFERER")
    referrer = referrer if referrer else reverse('zones')

    try:
        domain_token = jwt.decode(
            request.GET.get("domain_token"), settings.DOMAINS_JWT_PUB, issuer='urn:as207960:domains',
            audience='urn:as207960:hexdns', options={'require': ['exp', 'iss', 'sub', 'domain']}, algorithms='ES384'
        )
    except jwt.exceptions.InvalidTokenError as e:
        return render(request, "dns_grpc/error.html", {
            "error": str(e),
            "back_url": referrer
        })

    if request.user.username != domain_token["sub"]:
        return render(request, "dns_grpc/error.html", {
            "error": "Token not for this user",
            "back_url": referrer
        })

    r = requests.post(
        f"{settings.DOMAINS_URL}/api/internal/domains/{domain_token['domain_id']}/set_dns/",
        headers={
            "Authorization": f"Bearer {client_token}"
        }
    )
    r.raise_for_status()

    existing_zone = models.DNSZone.objects.filter(zone_root=domain_token["domain"]).first()
    if existing_zone:
        existing_zone.active = True
        existing_zone.save()
        request.session["zone_notice"] = "We've updated the DNS servers for your domain to point to HexDNS. " \
                                         "It may take up to 24 hours for the updates to propagate."
        return redirect('edit_zone', existing_zone.id)

    zone_root = domain_token["domain"].lower()
    zone_error = utils.valid_zone(zone_root)
    if zone_error:
        return render(request, "dns_grpc/error.html", {
            "error": zone_error,
            "back_url": referrer
        })

    status, extra = utils.log_usage(
        request.user, redirect_uri=settings.EXTERNAL_URL_BASE + reverse('zones'),
        can_reject=True, off_session=False
    )
    if status == "error":
        return render(request, "dns_grpc/error.html", {
            "error": extra,
            "back_url": referrer
        })

    zone_obj = models.DNSZone(
        zone_root=domain_token["domain"],
        last_modified=timezone.now(),
        user=request.user,
        zsk_private=utils.get_priv_key_bytes(),
        charged=False,
        active=True,
    )
    zone_obj.save()
    request.session["zone_notice"] = "We've updated the DNS servers for your domain to point to HexDNS. " \
                                     "It may take up to 24 hours for the updates to propagate."

    if status == "redirect":
        return redirect(extra)

    return redirect('edit_zone', zone_obj.id)


@login_required
def create_domain_zone_list(request):
    client_token = django_keycloak_auth.clients.get_access_token()
    r = requests.get(
        f"{settings.DOMAINS_URL}/api/internal/domains/{request.user.username}/all",
        headers={
            "Authorization": f"Bearer {client_token}"
        }
    )

    domains = []

    if r.status_code != 404:
        r.raise_for_status()
        data = r.json()
        for domain in data["domains"]:
            zone_error = utils.valid_zone(domain["domain"])
            domain["error"] = zone_error
            domains.append(domain)

    return render(request, "dns_grpc/fzone/domain_zones.html", {
        "domains": domains
    })


@login_required
def edit_zone(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    dnssec_digest, dnssec_tag = utils.make_zone_digest(user_zone.zone_root)
    sharing_data = {
        "referrer": settings.OIDC_CLIENT_ID,
        "referrer_uri": request.build_absolute_uri()
    }
    sharing_data_uri = urllib.parse.urlencode(sharing_data)
    sharing_uri = f"{settings.KEYCLOAK_SERVER_URL}/auth/realms/{settings.KEYCLOAK_REALM}/account/resource/" \
                  f"{user_zone.resource_id}?{sharing_data_uri}"

    return render(
        request,
        "dns_grpc/fzone/zone.html",
        {
            "zone": user_zone,
            "dnssec_tag": dnssec_tag,
            "dnssec_digest": dnssec_digest,
            "sharing_uri": sharing_uri,
            "notice": request.session.pop("zone_notice", None)
        },
    )


@login_required
def delete_zone(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'delete'):
        raise PermissionDenied

    if request.method == "POST" and request.POST.get("delete") == "true":
        status, extra = utils.log_usage(
            user_zone.get_user(), extra=-1, redirect_uri=settings.EXTERNAL_URL_BASE + reverse('zones'),
            can_reject=True, off_session=False
        )
        if status == "error":
            return render(request, "dns_grpc/fzone/delete_zone.html", {
                "zone": user_zone,
                "error": extra
            })
        else:
            user_zone.delete()
            if status == "redirect":
                return redirect(extra)
            return redirect('zones')
    else:
        return render(request, "dns_grpc/fzone/delete_zone.html", {
            "zone": user_zone
        })


@login_required
def edit_zone_tsig(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    return render(
        request,
        "dns_grpc/fzone/zone_tsig.html",
        {"zone": user_zone, },
    )


@login_required
def create_address_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.AddressRecordForm(request.POST, instance=models.AddressRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.AddressRecordForm(instance=models.AddressRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create address record", "form": record_form, },
    )


@login_required
def edit_address_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.AddressRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.AddressRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.AddressRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit address record", "form": record_form, },
    )


@login_required
def delete_address_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.AddressRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete address record", "record": user_record, },
    )


@login_required
def create_dynamic_address_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.DynamicAddressRecordForm(request.POST, instance=models.DynamicAddressRecord(zone=user_zone))
        del record_form.fields['id']
        del record_form.fields['password']
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            instance.password = secrets.token_hex(32)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.DynamicAddressRecordForm(instance=models.DynamicAddressRecord(zone=user_zone))
        del record_form.fields['id']
        del record_form.fields['password']

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create dynamic address record", "form": record_form},
    )


@login_required
def edit_dynamic_address_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.DynamicAddressRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.DynamicAddressRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.DynamicAddressRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit dynamic address record", "form": record_form},
    )


@login_required
def delete_dynamic_address_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.DynamicAddressRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete dynamic address record", "record": user_record},
    )


@login_required
def create_aname_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.ANAMERecordForm(request.POST, instance=models.ANAMERecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.ANAMERecordForm(instance=models.ANAMERecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create ANAME record", "form": record_form, },
    )


@login_required
def edit_aname_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.ANAMERecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.ANAMERecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.ANAMERecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit ANAME record", "form": record_form, },
    )


@login_required
def delete_aname_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.ANAMERecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete ANAME record", "record": user_record, },
    )


@login_required
def create_cname_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.CNAMERecordForm(request.POST, instance=models.CNAMERecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.CNAMERecordForm(instance=models.CNAMERecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create CNAME record", "form": record_form, },
    )


@login_required
def edit_cname_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.CNAMERecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.CNAMERecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.CNAMERecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit CNAME record", "form": record_form, },
    )


@login_required
def delete_cname_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.CNAMERecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete CNAME record", "record": user_record, },
    )


@login_required
def create_mx_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.MXRecordForm(request.POST, instance=models.MXRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.MXRecordForm(instance=models.MXRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create MX record", "form": record_form, },
    )


@login_required
def edit_mx_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.MXRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.MXRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.MXRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit MX record", "form": record_form, },
    )


@login_required
def delete_mx_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.MXRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete MX record", "record": user_record, },
    )


@login_required
def create_ns_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.NSRecordForm(request.POST, instance=models.NSRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.NSRecordForm(instance=models.NSRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create NS record", "form": record_form, },
    )


@login_required
def edit_ns_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.NSRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.NSRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.NSRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit NS record", "form": record_form, },
    )


@login_required
def delete_ns_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.NSRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete NS record", "record": user_record, },
    )


@login_required
def create_txt_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.TXTRecordForm(request.POST, instance=models.TXTRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.TXTRecordForm(instance=models.TXTRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create TXT record", "form": record_form, },
    )


@login_required
def edit_txt_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.TXTRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.TXTRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.TXTRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit TXT record", "form": record_form, },
    )


@login_required
def delete_txt_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.TXTRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete TXT record", "record": user_record, },
    )


@login_required
def create_srv_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.SRVRecordForm(request.POST, instance=models.SRVRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.SRVRecordForm(instance=models.SRVRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create SRV record", "form": record_form, },
    )


@login_required
def edit_srv_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.SRVRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.SRVRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.SRVRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit SRV record", "form": record_form, },
    )


@login_required
def delete_srv_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.SRVRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete SRV record", "record": user_record, },
    )


@login_required
def create_caa_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.CAARecordForm(request.POST, instance=models.CAARecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.CAARecordForm(instance=models.CAARecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create CAA record", "form": record_form, },
    )


@login_required
def edit_caa_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.CAARecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.CAARecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.CAARecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit CAA record", "form": record_form, },
    )


@login_required
def delete_caa_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.CAARecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete CAA record", "record": user_record, },
    )


@login_required
def create_naptr_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.NAPTRRecordForm(request.POST, instance=models.NAPTRRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.NAPTRRecordForm(instance=models.NAPTRRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create NAPTR record", "form": record_form, },
    )


@login_required
def edit_naptr_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.NAPTRRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.NAPTRRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.NAPTRRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit NAPTR record", "form": record_form, },
    )


@login_required
def delete_naptr_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.NAPTRRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete NAPTR record", "record": user_record, },
    )


@login_required
def create_sshfp_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.SSHFPRecordForm(request.POST, instance=models.SSHFPRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.SSHFPRecordForm(instance=models.DynamicAddressRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create SSHFP record", "form": record_form, },
    )


@login_required
def edit_sshfp_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.SSHFPRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.SSHFPRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.SSHFPRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit SSHFP record", "form": record_form, },
    )


@login_required
def delete_sshfp_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.SSHFPRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete SSHFP record", "record": user_record, },
    )


@login_required
def create_ds_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.DSRecordForm(request.POST, instance=models.DSRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.DSRecordForm(instance=models.DSRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create DS record", "form": record_form, },
    )


@login_required
def edit_ds_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.DSRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.DSRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.DSRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit DS record", "form": record_form, },
    )


@login_required
def delete_ds_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.DSRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete DS record", "record": user_record, },
    )


@login_required
def create_loc_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.LOCRecordForm(request.POST, instance=models.LOCRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.LOCRecordForm(instance=models.LOCRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create LOC record", "form": record_form, },
    )


@login_required
def edit_loc_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.LOCRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.LOCRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.LOCRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit LOC record", "form": record_form, },
    )


@login_required
def delete_loc_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.LOCRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete LOC record", "record": user_record, },
    )


@login_required
def create_hinfo_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.HINFORecordForm(request.POST, instance=models.HINFORecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.HINFORecordForm(instance=models.HINFORecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create HINFO record", "form": record_form, },
    )


@login_required
def edit_hinfo_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.HINFORecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.HINFORecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.HINFORecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit HINFO record", "form": record_form, },
    )


@login_required
def delete_hinfo_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.HINFORecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete HINFO record", "record": user_record, },
    )


@login_required
def create_rp_record(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.RPRecordForm(request.POST, instance=models.RPRecord(zone=user_zone))
        if record_form.is_valid():
            instance = record_form.save(commit=False)
            user_zone.last_modified = timezone.now()
            instance.save()
            user_zone.save()
            return redirect("edit_zone", user_zone.id)
    else:
        record_form = forms.RPRecordForm(instance=models.RPRecord(zone=user_zone))

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create RP record", "form": record_form, },
    )


@login_required
def edit_rp_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.RPRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.RPRecordForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            record_form.save()
            return redirect("edit_zone", user_record.zone.id)
    else:
        record_form = forms.RPRecordForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit RP record", "form": record_form, },
    )


@login_required
def delete_rp_record(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.RPRecord, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.zone.last_modified = timezone.now()
            user_record.zone.save()
            user_record.delete()
            return redirect("edit_zone", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete RP record", "record": user_record, },
    )


@login_required
def create_zone_secret(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_zone = get_object_or_404(models.DNSZone, id=zone_id)

    if not user_zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.UpdateSecretForm(request.POST, instance=models.DNSZoneUpdateSecrets(zone=user_zone))
        del record_form.fields['id']
        if record_form.is_valid():
            record_form.save()
            return redirect("edit_zone_secrets", user_zone.id)
    else:
        record_form = forms.UpdateSecretForm(instance=models.DNSZoneUpdateSecrets(zone=user_zone))
        del record_form.fields['id']

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Create update secret", "form": record_form, },
    )


@login_required
def edit_zone_secret(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.DNSZoneUpdateSecrets, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        record_form = forms.UpdateSecretForm(request.POST, instance=user_record)
        if record_form.is_valid():
            user_record.save()
            return redirect("edit_zone_secrets", user_record.zone.id)
    else:
        record_form = forms.UpdateSecretForm(instance=user_record)

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Edit update secret", "form": record_form, },
    )


@login_required
def delete_zone_secret(request, record_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    user_record = get_object_or_404(models.DNSZoneUpdateSecrets, id=record_id)

    if not user_record.zone.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        if request.POST.get("delete") == "true":
            user_record.delete()
            return redirect("edit_zone_secrets", user_record.zone.id)

    return render(
        request,
        "dns_grpc/fzone/delete_record.html",
        {"title": "Delete update secret", "record": user_record, },
    )


@login_required
def import_zone_file(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    zone_obj = get_object_or_404(models.DNSZone, id=zone_id)

    if not zone_obj.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        import_form = forms.ZoneImportForm(request.POST)
        if import_form.is_valid():
            zone_data = import_form.cleaned_data["zone_data"]
            suffix = dnslib.DNSLabel(zone_obj.zone_root)
            p = dnslib.ZoneParser(zone_data, origin=suffix)
            try:
                records = list(p)
            except (dnslib.DNSError, ValueError) as e:
                import_form.errors["zone_data"] = (f"Invalid zone file: {str(e)}",)
            else:
                for record in records:
                    if record.rclass != dnslib.CLASS.IN:
                        continue
                    record_name = record.rname.stripSuffix(suffix)
                    if len(record_name.label) == 0:
                        record_name = dnslib.DNSLabel("@")
                    if record.rtype == dnslib.QTYPE.A:
                        r = models.AddressRecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.AAAA:
                        r = models.AddressRecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.CNAME:
                        r = models.CNAMERecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.MX:
                        r = models.MXRecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.NS and record_name != "@":
                        r = models.NSRecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.TXT:
                        r = models.TXTRecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.SRV:
                        r = models.SRVRecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.CAA:
                        r = models.CAARecord.from_rr(record, zone_obj)
                        r.save()
                    elif record.rtype == dnslib.QTYPE.NAPTR:
                        r = models.NAPTRRecord.from_rr(record, zone_obj)
                        r.save()
                return redirect('edit_zone', zone_id)
    else:
        import_form = forms.ZoneImportForm()

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Zone file import", "form": import_form},
    )


@login_required
def generate_dmarc(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    zone_obj = get_object_or_404(models.DNSZone, id=zone_id)

    if not zone_obj.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        gen_form = forms.DMARCForm(request.POST)
        if gen_form.is_valid():
            dmarc_data = f"v=DMARC1; p={gen_form.cleaned_data['policy']}"
            if gen_form.cleaned_data['subdomain_policy']:
                dmarc_data += f"; sp={gen_form.cleaned_data['subdomain_policy']}"
            if gen_form.cleaned_data['percentage']:
                dmarc_data += f"; pct={gen_form.cleaned_data['percentage']}"
            if gen_form.cleaned_data['dkim_alignment']:
                dmarc_data += f"; adkim={gen_form.cleaned_data['dkim_alignment']}"
            if gen_form.cleaned_data['spf_alignment']:
                dmarc_data += f"; aspf={gen_form.cleaned_data['spf_alignment']}"
            if gen_form.cleaned_data['report_interval']:
                dmarc_data += f"; ri={gen_form.cleaned_data['report_interval']}"
            if gen_form.cleaned_data['aggregate_feedback']:
                dmarc_data += f"; rua={gen_form.cleaned_data['aggregate_feedback']}"
            if gen_form.cleaned_data['failure_feedback']:
                dmarc_data += f"; ruf={gen_form.cleaned_data['failure_feedback']}"

            r = models.TXTRecord(
                zone=zone_obj,
                data=dmarc_data,
                ttl=86400,
                record_name="_dmarc"
            )
            r.save()
            return redirect('edit_zone', zone_id)
    else:
        gen_form = forms.DMARCForm()

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "DMARC Generate", "form": gen_form},
    )


@login_required
def setup_gsuite(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    zone_obj = get_object_or_404(models.DNSZone, id=zone_id)

    if not zone_obj.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST" and request.POST.get("setup") == "true":
        zone_obj.mxrecord_set.filter(record_name="@").delete()
        for r in (
                ("aspmx.l.google.com", 1),
                ("alt1.aspmx.l.google.com", 5),
                ("alt2.aspmx.l.google.com", 5),
                ("alt3.aspmx.l.google.com", 10),
                ("alt4.aspmx.l.google.com", 10),
        ):
            mx = models.MXRecord(
                zone=zone_obj,
                record_name="@",
                ttl=3600,
                exchange=r[0],
                priority=r[1]
            )
            mx.save()
        return redirect('edit_zone', zone_obj.id)

    return render(
        request,
        "dns_grpc/fzone/setup_gsuite.html",
        {"zone": zone_obj},
    )


@login_required
def setup_github_pages(request, zone_id):
    access_token = django_keycloak_auth.clients.get_active_access_token(oidc_profile=request.user.oidc_profile)
    zone_obj = get_object_or_404(models.DNSZone, id=zone_id)

    if not zone_obj.has_scope(access_token, 'edit'):
        raise PermissionDenied

    if request.method == "POST":
        gen_form = forms.GithubPagesForm(request.POST)
        if gen_form.is_valid():
            zone_obj.addressrecord_set.filter(record_name=gen_form.cleaned_data['record_name']).delete()
            for a in (
                    "185.199.108.153",
                    "185.199.109.153",
                    "185.199.110.153",
                    "185.199.111.153"
            ):
                addr = models.AddressRecord(
                    zone=zone_obj,
                    address=a,
                    record_name=gen_form.cleaned_data['record_name'],
                    ttl=3600,
                )
                addr.save()
            return redirect('edit_zone', zone_obj.id)
    else:
        gen_form = forms.GithubPagesForm()

    return render(
        request,
        "dns_grpc/fzone/edit_record.html",
        {"title": "Setup for GitHub Pages", "form": gen_form},
    )