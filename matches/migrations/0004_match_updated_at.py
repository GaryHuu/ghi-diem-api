from django.db import migrations, models


def backfill_updated_at(apps, schema_editor):
    """Seed existing rows from created_at so they are not all stamped with the
    migration time (which would make the dashboard order meaningless)."""
    Match = apps.get_model("matches", "Match")
    for match in Match.objects.all().iterator():
        Match.objects.filter(pk=match.pk).update(updated_at=match.created_at)


class Migration(migrations.Migration):
    dependencies = [
        ("matches", "0003_match_deleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.RunPython(backfill_updated_at, migrations.RunPython.noop),
    ]
