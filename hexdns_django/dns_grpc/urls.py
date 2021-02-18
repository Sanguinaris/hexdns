from django.urls import path, include
from . import views

urlpatterns = [
    path("", views.fzone.zones, name="zones"),
    path("create_zone/", views.fzone.create_zone, name="create_zone"),
    path("setup_domains_zone/", views.fzone.create_domains_zone, name="create_domains_zone"),
    path("setup_domain_zone_list/", views.fzone.create_domain_zone_list, name="create_domain_zone_list"),
    path("zone/<str:zone_id>/", views.fzone.edit_zone, name="edit_zone"),
    path("zone/<str:zone_id>/import_zone_file/", views.fzone.import_zone_file, name="import_zone_file"),
    path("zone/<str:zone_id>/generate_dmarc/", views.fzone.generate_dmarc, name="generate_dmarc"),
    path("zone/<str:zone_id>/setup_gsutie/", views.fzone.setup_gsuite, name="setup_gsuite"),
    path("zone/<str:zone_id>/setup_github_pages/", views.fzone.setup_github_pages, name="setup_github_pages"),
    path("zone/<str:zone_id>/tsig/", views.fzone.edit_zone_tsig, name="edit_zone_secrets"),
    path("zone/<str:zone_id>/tsig/create/", views.fzone.create_zone_secret, name="create_zone_secret"),
    path("tsig/<str:record_id>/", views.fzone.edit_zone_secret, name="edit_zone_secret"),
    path("tsig/<str:record_id>/delete/", views.fzone.delete_zone_secret, name="delete_zone_secret"),
    path("delete_zone/<str:zone_id>/", views.fzone.delete_zone, name="delete_zone"),
    path(
        "zone/<str:zone_id>/new_address/",
        views.fzone.create_address_record,
        name="create_address_record",
    ),
    path(
        "zone/<str:zone_id>/new_dynamic_address/",
        views.fzone.create_dynamic_address_record,
        name="create_dynamic_address_record",
    ),
    path(
        "zone/<str:zone_id>/new_aname/",
        views.fzone.create_aname_record,
        name="create_aname_record",
    ),
    path(
        "zone/<str:zone_id>/new_cname/",
        views.fzone.create_cname_record,
        name="create_cname_record",
    ),
    path(
        "zone/<str:zone_id>/new_mx/", views.fzone.create_mx_record, name="create_mx_record"
    ),
    path(
        "zone/<str:zone_id>/new_ns/", views.fzone.create_ns_record, name="create_ns_record"
    ),
    path(
        "zone/<str:zone_id>/new_txt/",
        views.fzone.create_txt_record,
        name="create_txt_record",
    ),
    path(
        "zone/<str:zone_id>/new_srv/",
        views.fzone.create_srv_record,
        name="create_srv_record",
    ),
    path(
        "zone/<str:zone_id>/new_caa/",
        views.fzone.create_caa_record,
        name="create_caa_record",
    ),
    path(
        "zone/<str:zone_id>/new_naptr/",
        views.fzone.create_naptr_record,
        name="create_naptr_record",
    ),
    path(
        "zone/<str:zone_id>/new_sshfp/",
        views.fzone.create_sshfp_record,
        name="create_sshfp_record",
    ),
    path(
        "zone/<str:zone_id>/new_ds/", views.fzone.create_ds_record, name="create_ds_record"
    ),
    path(
        "zone/<str:zone_id>/new_loc/", views.fzone.create_loc_record, name="create_loc_record"
    ),
    path(
        "zone/<str:zone_id>/new_hinfo/", views.fzone.create_hinfo_record, name="create_hinfo_record"
    ),
    path(
        "zone/<str:zone_id>/new_rp/", views.fzone.create_rp_record, name="create_rp_record"
    ),
    path(
        "records/address/<str:record_id>/",
        views.fzone.edit_address_record,
        name="edit_address_record",
    ),
    path(
        "records/address/<str:record_id>/delete/",
        views.fzone.delete_address_record,
        name="delete_address_record",
    ),
    path(
        "records/dynamic_address/<str:record_id>/",
        views.fzone.edit_dynamic_address_record,
        name="edit_dynamic_address_record",
    ),
    path(
        "records/dynamic_address/<str:record_id>/delete/",
        views.fzone.delete_dynamic_address_record,
        name="delete_dynamic_address_record",
    ),
    path(
        "records/aname/<str:record_id>/",
        views.fzone.edit_aname_record,
        name="edit_aname_record",
    ),
    path(
        "records/aname/<str:record_id>/delete/",
        views.fzone.delete_aname_record,
        name="delete_aname_record",
    ),
    path(
        "records/cname/<str:record_id>/",
        views.fzone.edit_cname_record,
        name="edit_cname_record",
    ),
    path(
        "records/cname/<str:record_id>/delete/",
        views.fzone.delete_cname_record,
        name="delete_cname_record",
    ),
    path("records/mx/<str:record_id>/", views.fzone.edit_mx_record, name="edit_mx_record"),
    path(
        "records/mx/<str:record_id>/delete/",
        views.fzone.delete_mx_record,
        name="delete_mx_record",
    ),
    path("records/ns/<str:record_id>/", views.fzone.edit_ns_record, name="edit_ns_record"),
    path(
        "records/ns/<str:record_id>/delete/",
        views.fzone.delete_ns_record,
        name="delete_ns_record",
    ),
    path(
        "records/txt/<str:record_id>/", views.fzone.edit_txt_record, name="edit_txt_record"
    ),
    path(
        "records/txt/<str:record_id>/delete/",
        views.fzone.delete_txt_record,
        name="delete_txt_record",
    ),
    path(
        "records/srv/<str:record_id>/", views.fzone.edit_srv_record, name="edit_srv_record"
    ),
    path(
        "records/srv/<str:record_id>/delete/",
        views.fzone.delete_srv_record,
        name="delete_srv_record",
    ),
    path(
        "records/caa/<str:record_id>/", views.fzone.edit_caa_record, name="edit_caa_record"
    ),
    path(
        "records/caa/<str:record_id>/delete/",
        views.fzone.delete_caa_record,
        name="delete_caa_record",
    ),
    path(
        "records/naptr/<str:record_id>/",
        views.fzone.edit_naptr_record,
        name="edit_naptr_record",
    ),
    path(
        "records/naptr/<str:record_id>/delete/",
        views.fzone.delete_naptr_record,
        name="delete_naptr_record",
    ),
    path(
        "records/sshfp/<str:record_id>/",
        views.fzone.edit_sshfp_record,
        name="edit_sshfp_record",
    ),
    path(
        "records/sshfp/<str:record_id>/delete/",
        views.fzone.delete_sshfp_record,
        name="delete_sshfp_record",
    ),
    path("records/ds/<str:record_id>/", views.fzone.edit_ds_record, name="edit_ds_record"),
    path(
        "records/ds/<str:record_id>/delete/",
        views.fzone.delete_ds_record,
        name="delete_ds_record",
    ),
    path("records/loc/<str:record_id>/", views.fzone.edit_loc_record, name="edit_loc_record"),
    path(
        "records/loc/<str:record_id>/delete/",
        views.fzone.delete_loc_record,
        name="delete_loc_record",
    ),
    path("records/hinfo/<str:record_id>/", views.fzone.edit_hinfo_record, name="edit_hinfo_record"),
    path(
        "records/hinfo/<str:record_id>/delete/",
        views.fzone.delete_hinfo_record,
        name="delete_hinfo_record",
    ),
    path("records/rp/<str:record_id>/", views.fzone.edit_rp_record, name="edit_rp_record"),
    path(
        "records/rp/<str:record_id>/delete/",
        views.fzone.delete_rp_record,
        name="delete_rp_record",
    ),
    path("reverse/", views.rzone.rzones, name="rzones"),
    path("rzone/<str:zone_id>/", views.rzone.edit_rzone, name="edit_rzone"),
    path(
        "rzone/<str:zone_id>/new_ptr/",
        views.rzone.create_r_ptr_record,
        name="create_r_ptr_record",
    ),
    path(
        "rzone/<str:zone_id>/new_ns/",
        views.rzone.create_r_ns_record,
        name="create_r_ns_record",
    ),
    path(
        "rrecords/ptr/<str:record_id>/",
        views.rzone.edit_r_ptr_record,
        name="edit_r_ptr_record",
    ),
    path(
        "rrecords/ptr/<str:record_id>/delete/",
        views.rzone.delete_r_ptr_record,
        name="delete_r_ptr_record",
    ),
    path(
        "rrecords/ns/<str:record_id>/",
        views.rzone.edit_r_ns_record,
        name="edit_r_ns_record",
    ),
    path(
        "rrecords/ns/<str:record_id>/delete/",
        views.rzone.delete_r_ns_record,
        name="delete_r_ns_record",
    ),
    path("create_szone/", views.szone.create_szone, name="new_szone"),
    path("secondary/", views.szone.szones, name="szones"),
    path("szone/<str:zone_id>/", views.szone.view_szone, name="view_szone"),
    path("szone/<str:zone_id>/edit/", views.szone.edit_szone, name="edit_szone"),
    path("delete_szone/<str:zone_id>/", views.szone.delete_szone, name="delete_szone"),
    path("dns_admin/", views.admin.index, name="admin_index"),
    path("dns_admin/create_zone/", views.admin.create_zone, name="admin_create_zone"),
    path("dns_admin/create_rzone/", views.admin.create_rzone, name="admin_create_rzone"),
    path("dns_admin/create_szone/", views.admin.create_szone, name="admin_create_szone"),
    path("dns_admin/zone/<str:zone_id>/delete/", views.admin.delete_zone, name="admin_delete_zone"),
    path("dns_admin/rzone/<str:zone_id>/delete/", views.admin.delete_rzone, name="admin_delete_rzone"),
    path("dns_admin/szone/<str:zone_id>/delete/", views.admin.delete_szone, name="admin_delete_szone"),
    path("checkip", views.dyndns.check_ip, name="check_ip"),
    path("nic/update", views.dyndns.update_ip, name="update_ip"),
    path('api/', include('dns_grpc.api.urls')),
]
