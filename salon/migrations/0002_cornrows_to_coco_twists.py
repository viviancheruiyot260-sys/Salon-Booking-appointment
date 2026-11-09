from django.db import migrations

OLD_SLUG = "cornrows"
NEW_SLUG = "coco-twists"
NEW_NAME = "Coco Twists"
NEW_DESCRIPTION = (
    "Short, defined twists on natural hair, finished with a light hold. "
    "Twist size is agreed with the studio."
)
OLD_DESCRIPTION = "Neat cornrows in a simple pattern. The final design is confirmed with the studio."


def forwards(apps, schema_editor):
    Service = apps.get_model("salon", "Service")
    if Service.objects.filter(slug=NEW_SLUG).exists():
        return
    Service.objects.filter(slug=OLD_SLUG).update(
        slug=NEW_SLUG,
        name=NEW_NAME,
        description=NEW_DESCRIPTION,
        image="",
    )


def backwards(apps, schema_editor):
    Service = apps.get_model("salon", "Service")
    if Service.objects.filter(slug=OLD_SLUG).exists():
        return
    Service.objects.filter(slug=NEW_SLUG).update(
        slug=OLD_SLUG,
        name="Cornrows",
        description=OLD_DESCRIPTION,
    )


class Migration(migrations.Migration):
    dependencies = [("salon", "0001_initial")]

    operations = [migrations.RunPython(forwards, backwards)]
