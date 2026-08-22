"""Recalcula family/variant/weight/is_italic das fontes já cadastradas.

Até aqui o formulário de upload gravava `family = name` sempre e `variant`
sempre "regular" — ignorando o que o próprio arquivo dizia. Toda fonte
carregada antes desta migração está, portanto, mal classificada: nenhuma
fica agrupada com sua contraparte em negrito, mesmo quando as duas foram
enviadas. Esta migração reabre cada arquivo já salvo e usa a mesma extração
de metadados do formulário para corrigir os quatro campos.
"""

from __future__ import annotations

from django.db import migrations


def recompute_metadata(apps, schema_editor):
    from fonts.services import inspect_font_file

    FontAsset = apps.get_model("fonts", "FontAsset")
    for font in FontAsset.objects.all():
        try:
            metadata = inspect_font_file(font.file.path)
        except Exception:
            # Arquivo ausente ou ilegível: mantém o que já estava gravado
            # em vez de derrubar a migração inteira por uma fonte quebrada.
            continue
        font.metadata = metadata
        font.family = metadata.get("detected_family") or font.family or font.name
        font.variant = metadata.get("detected_variant") or "Regular"
        font.weight = metadata.get("weight") or 400
        font.is_italic = bool(metadata.get("is_italic"))
        font.save(update_fields=["metadata", "family", "variant", "weight", "is_italic"])


def noop_reverse(apps, schema_editor):
    # Sem volta razoável: reverter significaria reintroduzir a classificação
    # errada (family=name, variant="regular") que esta migração corrige.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("fonts", "0004_fontasset_weight_and_italic"),
    ]

    operations = [
        migrations.RunPython(recompute_metadata, noop_reverse),
    ]
