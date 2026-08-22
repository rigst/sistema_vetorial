import io

import pikepdf
from django import forms
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image, ImageOps

from fonts.models import FontAsset

from .models import DocumentTemplate, TemplateField

IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "webp"}

# ColorSpace do PDF por modo do Pillow. Só entram modos de 8 bits por canal, que
# é o que o PDF representa direto, sem reamostrar.
PDF_COLORSPACES = {
    "L": pikepdf.Name.DeviceGray,
    "RGB": pikepdf.Name.DeviceRGB,
    "CMYK": pikepdf.Name.DeviceCMYK,
}

# Componentes por modo, para declarar o /N de um espaço de cor ICC embutido.
PDF_COMPONENTS = {"L": 1, "RGB": 3, "CMYK": 4}


def _can_reuse_jpeg(image: Image.Image, transposed: bool) -> bool:
    """Um JPEG baseline já está no formato que o PDF usa (DCTDecode): dá para
    embutir os bytes originais e não perder nada na conversão."""
    return (
        image.format == "JPEG"
        and image.mode in {"L", "RGB"}
        and not transposed
        and not image.info.get("progressive")
    )


def _colorspace_for(pdf: pikepdf.Pdf, mode: str, icc_profile: bytes | None):
    """Mantém o perfil ICC do original quando existe; sem ele o PDF usa o
    espaço de dispositivo correspondente ao modo."""
    if icc_profile and mode in PDF_COMPONENTS:
        profile_stream = pikepdf.Stream(pdf, icc_profile)
        profile_stream.N = PDF_COMPONENTS[mode]
        return pikepdf.Array([pikepdf.Name.ICCBased, profile_stream])
    return PDF_COLORSPACES[mode]


def _build_image_pdf(width: int, height: int, write_stream) -> bytes:
    """Monta um PDF de uma página com a imagem ocupando a página inteira.

    A página mede width x height pontos: com resolution=72 do PDF, 1 pixel da
    imagem vira 1 ponto, então a densidade original é preservada exatamente.
    """
    pdf = pikepdf.Pdf.new()
    stream = pikepdf.Stream(pdf, b"")
    write_stream(pdf, stream)
    stream.Type = pikepdf.Name.XObject
    stream.Subtype = pikepdf.Name.Image
    stream.Width = width
    stream.Height = height
    stream.BitsPerComponent = 8

    page = pdf.add_blank_page(page_size=(width, height))
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=stream))
    page.Contents = pikepdf.Stream(pdf, f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode())

    buffer = io.BytesIO()
    pdf.save(buffer)
    return buffer.getvalue()


def _image_to_pdf(uploaded, base_name: str) -> ContentFile:
    uploaded.seek(0)
    original_bytes = uploaded.read()
    try:
        image = Image.open(io.BytesIO(original_bytes))
        image.load()
    except Exception as exc:
        raise forms.ValidationError(
            "Não foi possível ler esta imagem. Verifique se o arquivo não está corrompido."
        ) from exc

    source_format = image.format
    source_size = image.size
    # Fotos de celular chegam giradas por EXIF; sem isto o fundo sai deitado.
    image = ImageOps.exif_transpose(image) or image
    transposed = image.size != source_size
    image.format = source_format

    if _can_reuse_jpeg(image, transposed):
        width, height = image.size
        mode = image.mode
        icc_profile = image.info.get("icc_profile")

        def write_original_jpeg(pdf, stream):
            stream.write(original_bytes, filter=pikepdf.Name.DCTDecode)
            stream.ColorSpace = _colorspace_for(pdf, mode, icc_profile)

        return ContentFile(
            _build_image_pdf(width, height, write_original_jpeg), name=f"{base_name}.pdf"
        )

    if image.mode in {"RGBA", "LA", "PA"} or (image.mode == "P" and "transparency" in image.info):
        # A página do PDF é opaca: o alfa é achatado sobre branco, como antes.
        converted = image.convert("RGBA")
        background = Image.new("RGB", converted.size, (255, 255, 255))
        background.paste(converted, mask=converted.getchannel("A"))
        image = background
    elif image.mode not in PDF_COLORSPACES:
        image = image.convert("RGB")

    width, height = image.size
    mode = image.mode
    # O achatamento do alfa cria uma imagem nova; o perfil só vale se o modo
    # continuou o mesmo que o arquivo trazia.
    icc_profile = image.info.get("icc_profile")
    raw_pixels = image.tobytes()

    def write_raw_pixels(pdf, stream):
        # Sem filter=: o pikepdf comprime com Flate ao salvar, que é sem perdas.
        stream.write(raw_pixels)
        stream.ColorSpace = _colorspace_for(pdf, mode, icc_profile)

    return ContentFile(_build_image_pdf(width, height, write_raw_pixels), name=f"{base_name}.pdf")


class DocumentTemplateForm(forms.ModelForm):
    def clean_background_pdf(self):
        uploaded = self.cleaned_data.get("background_pdf")
        if not uploaded:
            return self.instance.background_pdf
        name = uploaded.name.lower()
        suffix = name.rsplit(".", 1)[-1] if "." in name else ""
        if suffix in IMAGE_SUFFIXES:
            uploaded.seek(0)
            base_name = uploaded.name.rsplit(".", 1)[0].rsplit("/", 1)[-1] or "fundo"
            return _image_to_pdf(uploaded, base_name)
        if suffix != "pdf":
            raise forms.ValidationError("Envie um PDF, PNG, JPG ou WebP para o fundo do template.")
        uploaded.seek(0)
        try:
            with pikepdf.Pdf.open(uploaded) as pdf:
                if len(pdf.pages) != 1:
                    raise forms.ValidationError("O template deve ter exatamente 1 página.")
        except Exception as exc:
            uploaded.seek(0)
            if isinstance(exc, forms.ValidationError):
                raise
            raise forms.ValidationError(
                "Não foi possível ler este PDF. Verifique se o arquivo não está corrompido."
            ) from exc
        uploaded.seek(0)
        return uploaded

    def save(self, commit=True):
        instance = super().save(commit=False)
        base_slug = slugify(instance.name) or "template"
        slug = base_slug
        counter = 2
        while (
            DocumentTemplate.objects.filter(user=instance.user, slug=slug)
            .exclude(pk=instance.pk)
            .exists()
        ):
            slug = f"{base_slug}-{counter}"
            counter += 1
        instance.slug = slug
        instance.page_count = 1
        if commit:
            instance.save()
        return instance

    class Meta:
        model = DocumentTemplate
        fields = ["name", "background_pdf"]
        labels = {
            "name": "Nome",
            "background_pdf": "Fundo (PDF, PNG, JPG ou WebP)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Certificado Base 2026"}),
            "background_pdf": forms.FileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg,.webp"}),
        }


class TemplateFieldForm(forms.ModelForm):
    class Meta:
        model = TemplateField
        fields = [
            "name",
            "excel_column",
            "value_type",
            "font",
            "font_size",
            "text_align",
            "text_transform",
            "transform_exceptions",
            "color",
            "line_height",
            "max_lines",
            "integer_min_digits",
            "integer_keep_sign",
            "empty_value",
            "trim_whitespace",
            "overflow_mode",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "nome"}),
            "excel_column": forms.NumberInput(attrs={"placeholder": "1", "min": "1"}),
            "transform_exceptions": forms.TextInput(
                attrs={"placeholder": "de, da, do, dos, das, e, com"}
            ),
            "empty_value": forms.TextInput(attrs={"placeholder": "Valor quando vazio"}),
            "color": forms.TextInput(attrs={"placeholder": "#000000"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["font"].queryset = FontAsset.objects.filter(user=user, is_active=True).order_by(
            "name"
        )
