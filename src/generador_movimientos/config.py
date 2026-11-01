import random
from dataclasses import dataclass, field
from datetime import date
from typing import List


@dataclass
class DateRange:
    start: date
    end: date


@dataclass
class Movement:
    fecha: str
    concepto: str
    movimiento: str
    importe: float


@dataclass
class BillingEntity:
    concepto: str
    base_amount: float
    variation: float = 0.0
    reference: str = ""

    def random_amount(self) -> float:
        if self.variation <= 0:
            return self.base_amount
        delta = self.base_amount * self.variation / 100.0
        return round(self.base_amount + random.uniform(-delta, delta), 2)


TRANSFER_SERVICES = [
    "mantenimiento web",
    "seo posicionamiento",
    "asesoría fiscal",
    "asesoría laboral",
    "suministros oficina",
    "publicidad digital",
    "limpieza local",
    "traducción documentos",
    "transporte mercancía",
    "reparación equipos",
    "diseño gráfico",
    "hosting y dominios",
    "seguridad de red",
    "copywrite contenido",
    "publicidad radio local",
    "electricidad oficina",
]

COBRO_CONCEPTS = [
    "Cobro proyecto web",
    "Cobro servicio consultoría",
    "Cobro facturación diseño",
    "Cobro mantenimiento aplicacion",
    "Cobro desarrollo frontend",
    "Cobro campañas marketing",
    "Cobro formación corporativa",
    "Cobro migración datos",
    "Cobro auditoría técnica",
    "Cobro integración API",
    "Cobro soporte mensual",
    "Cobro suscripción software",
    "Cobro desarrollo móvil",
    "Cobro analítica de datos",
    "Cobro implantación CRM",
    "Cobro pasarela de pago",
]

NOISE_COMMERCE = [
    "compra supermercado",
    "compra ferretería",
    "compra librería",
    "consumo combustible",
    "restauración",
    "aparcamiento",
    "compra panadería",
    "compra tintorería",
    "abono transporte",
]


@dataclass
class GeneratorConfig:
    billing_entities: List[BillingEntity] = field(default_factory=lambda: [
        BillingEntity("Adeudo telefonía", 95.0, 10.0),
        BillingEntity("Adeudo luz", 68.2, 10.0),
        BillingEntity("Adeudo agua", 24.6, 10.0),
        BillingEntity("Adeudo gas", 41.9, 10.0),
        BillingEntity("Adeudo internet", 45.9, 10.0),
        BillingEntity("Adeudo alquiler local", 3000.0, 0.0),
        BillingEntity("Adeudo seguro", 39.9, 0.0),
        BillingEntity("Adeudo gestoría", 87.3, 0.0),
        BillingEntity("Adeudo limpieza", 92.4, 0.0),
        BillingEntity("Adeudo vigilancia", 78.5, 0.0),
        BillingEntity("Adeudo suministros", 56.8, 10.0),
        BillingEntity("Adeudo software", 15.99, 0.0),
    ])
    transfer_services: List[str] = field(default_factory=lambda: TRANSFER_SERVICES)
    cobro_concepts: List[str] = field(default_factory=lambda: COBRO_CONCEPTS)

    def assign_references(self) -> "GeneratorConfig":
        for entity in self.billing_entities:
            if not entity.reference:
                entity.reference = f"{random.randint(0, 999999999999):012d}"
        return self


class ConfigError(Exception):
    pass
