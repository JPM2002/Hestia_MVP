# gateway_app/services/faq_llm.py
"""
FAQ helper module for the WhatsApp guest assistant.

Responsibilities:
- Define a simple FAQ data structure (key, question, answer).
- Provide a best-effort matcher from a user's short message to an FAQ entry.
- Optionally use an LLM to answer based on the FAQ list when lexical matching fails.

Typical usage from the state machine / webhook:

    from gateway_app.services import faq_llm

    answer = faq_llm.answer_faq(inbound_text)
    if answer:
        # send FAQ answer and optionally keep conversation in FAQ state
        ...

You can later:
- Replace FAQ_ITEMS with hotel-specific items loaded from a DB.
- Tune thresholds or completely replace matching logic.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Any


from openai import OpenAI

logger = logging.getLogger(__name__)

_client = OpenAI()
FAQ_LLM_MODEL = os.getenv("FAQ_LLM_MODEL", "gpt-4.1-mini")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FAQItem:
    key: str
    q: str
    a: str


#: Default, generic FAQ set. Replace/extend per hotel as needed.
FAQ_ITEMS: List[Dict[str, str]] = [
    # 1. Check-in / Check-out
    {"key": "checkin_time", "q": "¿A qué hora es el check-in?", "a": "El check-in es a partir de las 14:00 hrs."},
    {"key": "early_checkin", "q": "¿Puedo hacer check-in antes de la hora?", "a": "Sí, siempre sujeto a la disponibilidad del momento; de lo contrario puede aplicar un cargo adicional."},
    {"key": "checkout_time", "q": "¿A qué hora es el check-out?", "a": "El check-out es hasta las 12:00 hrs."},
    {"key": "late_checkout", "q": "¿Puedo dejar la habitación más tarde?", "a": "Sí, con un recargo del 50% hasta las 16:00 hrs; después de ese horario se cobra una noche adicional."},
    {"key": "express_checkout", "q": "¿Cómo puedo hacer el check-out rápido?", "a": "Realizando el pago completo en recepción de manera anticipada; así el check-out es más rápido."},
    {"key": "late_checkout_payment", "q": "¿Puedo pagar el late check-out?", "a": "Sí, puede pagar el late check-out directamente en recepción."},
    {"key": "key_drop", "q": "¿Dónde dejo la llave al salir?", "a": "Puede llevarla consigo o bien dejarla en recepción."},
    {"key": "luggage_after_checkout", "q": "¿Puedo dejar mi equipaje después del check-out?", "a": "Sí, puede dejar su equipaje en custodia."},
    {"key": "early_checkin_cost", "q": "¿Cuánto cuesta el early check-in?", "a": "Si ingresa antes de las 10:00 hrs corresponde a una noche adicional; después de ese horario se aplica un recargo del 50%, siempre sujeto a disponibilidad."},
    {"key": "online_checkin", "q": "¿Se puede hacer el check-in online?", "a": "No, por el momento no contamos con check-in online."},

    # 2. Equipaje y transporte
    {"key": "luggage_storage_place", "q": "¿Dónde puedo guardar mi maleta?", "a": "Puede guardar su maleta en el servicio de custodia del hotel."},
    {"key": "luggage_storage", "q": "¿Tienen custodia de equipaje?", "a": "Sí, contamos con custodia de equipaje para los huéspedes."},
    {"key": "luggage_storage_time", "q": "¿Cuánto tiempo pueden guardar mis cosas?", "a": "Podemos guardar su equipaje el tiempo que estime necesario antes de su salida."},
    {"key": "luggage_to_airport", "q": "¿Pueden enviarme mi maleta al aeropuerto?", "a": "Sí, previo acuerdo y con costo adicional."},
    {"key": "airport_transfer", "q": "¿Tienen servicio de transporte al aeropuerto?", "a": "Sí, se puede solicitar en recepción."},
    {"key": "transfer_cost", "q": "¿Cuánto cuesta el transfer?", "a": "El valor del transfer se debe consultar directamente en recepción."},
    {"key": "taxi_booking", "q": "¿Puedo reservar un taxi desde aquí?", "a": "Sí, puede solicitar un taxi en recepción."},
    {"key": "parking_available", "q": "¿Tienen estacionamiento?", "a": "Sí, contamos con estacionamiento subterráneo sin costo para los huéspedes."},
    {"key": "parking_included", "q": "¿Está incluido el estacionamiento?", "a": "Sí, el estacionamiento está incluido y no tiene costo para los huéspedes."},
    {"key": "ev_chargers", "q": "¿Tienen cargadores eléctricos para autos?", "a": "No, no contamos con cargadores para autos eléctricos."},

    # 3. Habitación
    {"key": "rooms_with_balcony", "q": "¿Tienen habitaciones con balcón?", "a": "No, no contamos con habitaciones con balcón."},
    {"key": "room_change", "q": "¿Puedo cambiar de habitación?", "a": "Sí, puede solicitar el cambio en recepción, sujeto a disponibilidad."},
    {"key": "rooms_with_view", "q": "¿Tienen vista a la ciudad o al mar?", "a": "No, no contamos con habitaciones con vista a la ciudad o al mar."},
    {"key": "quiet_room", "q": "¿Puedo pedir una habitación más silenciosa?", "a": "Sí, puede solicitar una habitación más silenciosa en recepción, sujeta a disponibilidad."},
    {"key": "extra_pillows", "q": "¿Puedo pedir almohadas extra?", "a": "Sí, puede solicitar almohadas extra en recepción."},
    {"key": "iron_available", "q": "¿Tienen plancha?", "a": "Sí, puede solicitar una plancha en recepción."},
    {"key": "ac_remote_location", "q": "¿Dónde puedo encontrar el control del aire acondicionado?", "a": "Si no lo encuentra en la habitación, puede solicitar ayuda o un control adicional en recepción."},
    {"key": "temperature_control", "q": "¿Puedo regular la temperatura?", "a": "Sí, puede regular la temperatura; si tiene dudas, consulte en recepción."},
    {"key": "minibar", "q": "¿Tienen minibar?", "a": "Sí, cada habitación cuenta con minibar."},
    {"key": "safe_usage", "q": "¿Cómo se abre la caja fuerte?", "a": "Debe accionar la caja fuerte ingresando un código de 4 dígitos."},
    {"key": "baby_cot", "q": "¿Puedo pedir una cuna para mi bebé?", "a": "Sí, puede solicitar una cuna en recepción, sujeta a disponibilidad."},
    {"key": "connecting_rooms", "q": "¿Tienen habitaciones conectadas?", "a": "Sí, puede solicitar habitaciones conectadas en recepción, sujetas a disponibilidad."},
    {"key": "extra_bed", "q": "¿Puedo pedir una cama adicional?", "a": "No contamos con camas adicionales."},
    {"key": "smoking_in_room", "q": "¿Puedo fumar en la habitación?", "a": "No, el hotel es completamente no fumador; no está permitido fumar en las habitaciones."},
    {"key": "non_smoking_hotel", "q": "¿Tienen habitaciones para no fumadores?", "a": "Sí, el hotel completo es no fumador."},
    {"key": "tv_usage", "q": "¿Cómo se usa la TV?", "a": "La TV se maneja mediante el control remoto disponible en la habitación."},
    {"key": "tv_channels", "q": "¿Qué canales de televisión tienen?", "a": "Contamos con una variedad de canales; en la habitación encontrará una cartilla con el detalle de los canales."},
    {"key": "smart_tv", "q": "¿Tienen Netflix o Smart TV?", "a": "Las habitaciones cuentan con Smart TV; puede usar sus propias cuentas en las aplicaciones disponibles."},
    {"key": "phone_charging", "q": "¿Dónde puedo cargar mi celular?", "a": "En los enchufes disponibles en cada habitación."},
    {"key": "windows_openable", "q": "¿Se puede abrir la ventana?", "a": "Sí, se pueden abrir las ventanas de la habitación."},

    # 4. Limpieza / Housekeeping
    {"key": "cleaning_hours", "q": "¿A qué hora limpian las habitaciones?", "a": "El servicio de limpieza se realiza aproximadamente entre las 09:00 y las 16:00 hrs."},
    {"key": "cleaning_later", "q": "¿Puedo pedir que limpien más tarde?", "a": "Sí, puede solicitar que la limpieza se realice más tarde dentro del horario de servicio."},
    {"key": "no_cleaning", "q": "¿Puedo pedir que no entren a limpiar?", "a": "Sí, puede colocar el letrero de 'No molestar' en la puerta para que no ingresen a limpiar."},
    {"key": "new_towels", "q": "¿Cómo pido toallas nuevas?", "a": "Puede solicitar toallas nuevas llamando directamente a recepción y marcando el 100."},
    {"key": "more_amenities", "q": "¿Puedo pedir más jabón o shampoo?", "a": "Sí, puede solicitar más amenities llamando a recepción y marcando el 100."},
    {"key": "sheets_change", "q": "¿Pueden cambiar las sábanas hoy?", "a": "Sí, las sábanas pueden ser cambiadas todos los días."},
    {"key": "extra_blanket", "q": "¿Puedo pedir una frazada extra?", "a": "En cada clóset de las habitaciones hay una frazada extra disponible."},
    {"key": "laundry_service", "q": "¿Puedo dejar ropa para lavandería?", "a": "No, el hotel no cuenta con servicio de lavandería."},
    {"key": "laundry_time", "q": "¿Cuánto demora el servicio de lavandería?", "a": "El hotel no cuenta con servicio de lavandería."},
    {"key": "ironing_service", "q": "¿Tienen planchado o tintorería?", "a": "El hotel no cuenta con servicio de lavandería ni tintorería."},

    # 5. Desayuno / Restaurante / Bar
    {"key": "breakfast_time", "q": "¿A qué hora sirven el desayuno?", "a": "De lunes a viernes de 06:30 a 10:30 hrs, y sábados, domingos y festivos de 07:00 a 11:00 hrs."},
    {"key": "breakfast_place", "q": "¿Dónde se sirve el desayuno?", "a": "El desayuno se sirve en el restaurante del hotel."},
    {"key": "breakfast_included", "q": "¿Está incluido el desayuno?", "a": "Sí, en todas nuestras tarifas está incluido el desayuno."},
    {"key": "breakfast_room_service", "q": "¿Puedo pedir el desayuno a la habitación?", "a": "No, no contamos con servicio de room service para desayuno."},
    {"key": "menu_options", "q": "¿Qué opciones tiene el menú?", "a": "Contamos con carta y sugerencias del chef."},
    {"key": "vegetarian_vegan", "q": "¿Tienen opciones vegetarianas o veganas?", "a": "Sí, consulte en el restaurante por las opciones vegetarianas o veganas disponibles."},
    {"key": "gluten_free", "q": "¿Tienen menú sin gluten?", "a": "Sí, consulte en el restaurante por las opciones sin gluten."},
    {"key": "restaurant_opening", "q": "¿A qué hora abre el restaurante?", "a": "El servicio está disponible desde las 06:30 hrs en adelante de lunes a viernes."},
    {"key": "restaurant_reservation", "q": "¿Puedo hacer una reserva?", "a": "Sí, puede hacer una reserva consultando en el restaurante."},
    {"key": "bar_cafeteria", "q": "¿Tienen bar o cafetería?", "a": "Sí, contamos con servicio de bar o cafetería; consulte en el restaurante."},
    {"key": "kitchen_hours", "q": "¿Hasta qué hora sirven comida?", "a": "Los horarios de cocina pueden consultarse directamente en el restaurante."},
    {"key": "room_service", "q": "¿Tienen servicio a la habitación?", "a": "No, no contamos con servicio de room service."},
    {"key": "room_service_how", "q": "¿Cómo hago un pedido de room service?", "a": "No contamos con servicio de room service."},
    {"key": "special_occasions", "q": "¿Puedo pedir algo especial para una ocasión?", "a": "Sí, puede coordinar algo especial consultando en el restaurante."},
    {"key": "external_food_apps", "q": "¿Se puede pedir comida desde apps externas?", "a": "No, no está permitido pedir comida desde aplicaciones externas."},
    {"key": "free_bottled_water", "q": "¿Tienen agua embotellada gratuita?", "a": "No, no contamos con agua embotellada gratuita."},

    # 6. Internet / Tecnología
    {"key": "wifi_password", "q": "¿Cuál es la clave del wifi?", "a": "La clave del wifi es Pastene120."},
    {"key": "wifi_free", "q": "¿El wifi es gratuito?", "a": "Sí, el wifi es gratuito para los huéspedes."},
    {"key": "wifi_signal_best", "q": "¿Dónde llega mejor la señal?", "a": "La cobertura de wifi puede variar dentro del hotel; si tiene problemas de señal, por favor contacte a recepción."},
    {"key": "guest_computers", "q": "¿Hay computadoras disponibles para huéspedes?", "a": "Sí, en el lobby del hotel hay un computador disponible para los huéspedes."},
    {"key": "printing_docs", "q": "¿Puedo imprimir un documento?", "a": "Sí, puede enviar su documento a imprimir a recepción al correo recepcion-pastene@dahoteles.com."},
    {"key": "videocalls_lobby", "q": "¿Puedo hacer videollamadas desde el lobby?", "a": "No es recomendable por el ruido; se sugiere consultar por la disponibilidad de una sala de reuniones."},
    {"key": "usb_adapters", "q": "¿Tienen puertos USB o adaptadores?", "a": "Contamos con adaptadores disponibles en recepción."},
    {"key": "fast_charging", "q": "¿Tienen servicio de carga rápida?", "a": "No contamos con servicio de carga rápida."},
    {"key": "wifi_pool_gym", "q": "¿El wifi llega hasta la piscina o gimnasio?", "a": "No; además, el hotel no cuenta con gimnasio ni piscina."},

    # 7. Instalaciones y servicios
    {"key": "pool", "q": "¿Tienen piscina?", "a": "No contamos con piscina."},
    {"key": "pool_opening", "q": "¿A qué hora abre la piscina?", "a": "No contamos con piscina."},
    {"key": "pool_heated", "q": "¿Está climatizada la piscina?", "a": "No contamos con piscina."},
    {"key": "gym", "q": "¿Tienen gimnasio?", "a": "No contamos con gimnasio."},
    {"key": "gym_opening", "q": "¿A qué hora abre el gimnasio?", "a": "No contamos con gimnasio."},
    {"key": "spa", "q": "¿Tienen spa?", "a": "No contamos con spa."},
    {"key": "massage_booking", "q": "¿Cómo puedo reservar un masaje?", "a": "No contamos con spa ni servicio de masajes."},
    {"key": "sauna_jacuzzi", "q": "¿Tienen sauna o jacuzzi?", "a": "No contamos con spa, sauna ni jacuzzi."},
    {"key": "hair_beauty", "q": "¿Tienen servicio de peluquería o estética?", "a": "No contamos con servicio de peluquería o estética."},
    {"key": "coworking", "q": "¿Tienen áreas para trabajar o coworking?", "a": "No contamos con áreas de coworking."},
    {"key": "events_room", "q": "¿Puedo usar el salón de eventos?", "a": "Sí, el uso del salón de eventos está siempre sujeto a disponibilidad."},
    {"key": "terrace_rooftop", "q": "¿Tienen terraza o rooftop?", "a": "Sí, contamos con una terraza en el primer piso."},
    {"key": "babysitting", "q": "¿Tienen servicio de babysitting?", "a": "No contamos con servicio de babysitting."},
    {"key": "kids_games", "q": "¿Tienen juegos para niños?", "a": "No contamos con juegos para niños."},
    {"key": "visitors_policy", "q": "¿Puedo recibir visitas?", "a": "Sí, toda visita debe registrarse en recepción."},

    # 8. Pagos y facturación de la habitación
    {"key": "pay_with_card", "q": "¿Puedo pagar con tarjeta?", "a": "Sí, puede pagar con tarjeta."},
    {"key": "bank_transfer", "q": "¿Aceptan transferencias?", "a": "Sí, aceptamos transferencias."},
    {"key": "pay_in_dollars", "q": "¿Puedo pagar con dólares?", "a": "Sí, aceptamos pago en dólares."},
    {"key": "split_payment", "q": "¿Puedo dividir el pago entre varias personas?", "a": "Sí, es posible dividir el pago entre varias personas."},
    {"key": "invoice_or_receipt", "q": "¿Entregan boleta o factura?", "a": "Sí, entregamos boleta o factura."},
    {"key": "invoice_by_email", "q": "¿Puedo recibir una copia de la factura por correo?", "a": "Sí, puede solicitar una copia de la factura por correo electrónico."},
    {"key": "deposit_required", "q": "¿Cobran depósito o garantía?", "a": "Sí, cobramos un depósito o garantía."},
    {"key": "deposit_return", "q": "¿Cuándo devuelven la garantía?", "a": "Al momento del check-out se hace efectiva la devolución de la garantía."},
    {"key": "tax_exempt_foreigners", "q": "¿Cobran impuesto adicional a extranjeros?", "a": "No; los huéspedes extranjeros no pagan IVA (19%) siempre que presenten su pasaporte, tarjeta de ingreso al país (PDI) y paguen su cuenta en dólares."},
    {"key": "lost_key", "q": "¿Qué pasa si pierdo mi llave o tarjeta de acceso?", "a": "Debe solicitar una nueva llave o tarjeta en recepción."},
    {"key": "pay_restaurant_separately", "q": "¿Se puede pagar aparte el consumo en Restaurant?", "a": "Sí, el consumo en el restaurante se puede pagar por separado."},

    # 9. Recepción / Atención
    {"key": "contact_reception", "q": "¿Cómo me comunico con recepción desde la habitación?", "a": "Puede comunicarse con recepción marcando el número 100 o 101 desde el teléfono de la habitación."},
    {"key": "emergency_number", "q": "¿Cuál es el número de emergencia del hotel?", "a": "El número de emergencia del hotel se encuentra indicado en su habitación; ante dudas, consulte en recepción."},
    {"key": "talk_to_manager", "q": "¿Puedo hablar con el gerente?", "a": "Sí, puede solicitar hablar con el gerente a través de recepción."},
    {"key": "help_other_language", "q": "¿Puedo pedir asistencia en otro idioma?", "a": "Sí, consulte en recepción por asistencia en otros idiomas."},
    {"key": "comments_complaints", "q": "¿Dónde puedo dejar un comentario o reclamo?", "a": "Puede dejar su comentario o reclamo directamente en recepción."},
    {"key": "itinerary_help", "q": "¿Puedo pedir ayuda con mi itinerario?", "a": "Sí, recepción puede ayudarle a revisar y organizar su itinerario."},
    {"key": "wake_up_service", "q": "¿Tienen servicio de despertador?", "a": "Sí, contamos con servicio de despertador."},
    {"key": "doctor_available", "q": "¿Tienen médico disponible?", "a": "Contamos con contactos de médico a domicilio; consulte en recepción."},
    {"key": "first_aid", "q": "¿Tienen botiquín o primeros auxilios?", "a": "Sí, disponemos de botiquín y primeros auxilios en recepción."},
    {"key": "umbrellas", "q": "¿Tienen paraguas para prestar?", "a": "No, no contamos con paraguas para préstamo."},

    # 10. Turismo / Actividades
    {"key": "tourist_places", "q": "¿Qué lugares turísticos recomiendan cerca?", "a": "Recomendamos el Parque Metropolitano Cerro San Cristóbal, el Parque Bicentenario y el Centro Cívico y Cultural de Santiago."},
    {"key": "tours_tickets", "q": "¿Dónde puedo comprar entradas a tours?", "a": "En recepción contamos con algunas alternativas para la compra de tours."},
    {"key": "agencies_deals", "q": "¿Tienen convenios con agencias?", "a": "Sí, contamos con convenios con agencias; consulte en recepción."},
    {"key": "city_maps", "q": "¿Tienen mapas de la ciudad?", "a": "Sí, disponemos de mapas de la ciudad en recepción."},
    {"key": "money_exchange", "q": "¿Dónde puedo cambiar dinero?", "a": "Puede cambiar dinero en casas de cambio cercanas al hotel."},
    {"key": "car_rental", "q": "¿Dónde puedo arrendar un auto?", "a": "El hotel no cuenta con servicio de arriendo de autos."},
    {"key": "nearest_supermarket", "q": "¿Dónde queda el supermercado más cercano?", "a": "El supermercado más cercano se encuentra a menos de dos cuadras del hotel."},
    {"key": "souvenirs", "q": "¿Dónde puedo comprar recuerdos?", "a": "En el centro de Santiago, en ferias artesanales y en el Pueblito Los Dominicos."},
    {"key": "nearby_restaurants", "q": "¿Qué restaurantes recomiendan cerca?", "a": "Hay una gran variedad de restaurantes en las calles cercanas al hotel."},
    {"key": "where_to_run", "q": "¿Dónde puedo salir a caminar o trotar?", "a": "A solo dos cuadras está Av. Andrés Bello, que cuenta con un parque central extenso para hacer deporte."},

    # 11. Mascotas
    {"key": "pets_allowed", "q": "¿Aceptan mascotas?", "a": "No, no aceptamos mascotas."},
    {"key": "pets_size", "q": "¿Qué tamaño máximo aceptan?", "a": "No aceptamos mascotas."},
    {"key": "pets_extra_cost", "q": "¿Cobra algún costo adicional?", "a": "No hay cargos por mascotas, ya que no están permitidas."},
    {"key": "pets_alone_in_room", "q": "¿Puedo dejar sola a mi mascota en la habitación?", "a": "No se permiten mascotas en el hotel."},
    {"key": "pets_areas", "q": "¿Tienen áreas para pasear perros?", "a": "No contamos con áreas para pasear mascotas."},
    {"key": "pets_beds_bowls", "q": "¿Tienen camas o platos para mascotas?", "a": "No contamos con camas ni platos para mascotas."},

    # 12. Reservas
    {"key": "modify_reservation", "q": "¿Puedo modificar mi reserva?", "a": "Sí, puede modificar su reserva en recepción."},
    {"key": "cancel_reservation", "q": "¿Puedo cancelar sin costo?", "a": "Sí, siempre y cuando esté dentro del tiempo permitido (24 horas antes); gestione la cancelación en recepción."},
    {"key": "add_nights", "q": "¿Puedo agregar noches extra?", "a": "Sí, puede agregar noches extra en recepción."},
    {"key": "change_room_type", "q": "¿Puedo cambiar el tipo de habitación?", "a": "Sí, puede solicitar el cambio de tipo de habitación en recepción, sujeto a disponibilidad."},
    {"key": "pay_at_hotel", "q": "¿Puedo pagar la reserva directamente en el hotel?", "a": "Sí, puede pagar la reserva directamente en el hotel, en recepción."},
    {"key": "reservation_received", "q": "¿Recibieron mi reserva?", "a": "Puede confirmar el estado de su reserva directamente en recepción."},
    {"key": "reserve_for_someone_else", "q": "¿Puedo reservar para otra persona?", "a": "Sí, puede realizar una reserva para otra persona en recepción."},
    {"key": "reserve_by_phone_whatsapp", "q": "¿Puedo reservar por teléfono o WhatsApp?", "a": "Sí, puede reservar por teléfono o por correo electrónico (no por WhatsApp)."},
    {"key": "special_room_occasion", "q": "¿Puedo pedir una habitación especial para aniversario o luna de miel?", "a": "Sí, puede solicitar una habitación especial para aniversario o luna de miel en recepción."},
    {"key": "loyalty_program", "q": "¿Existe algún programa de beneficios/Fidelización dentro del hotel?", "a": "No contamos con programa de beneficios o fidelización."},
    {"key": "reserve_with_points", "q": "¿Puedo reservar con puntos o beneficios?", "a": "No contamos con sistema de reservas con puntos o beneficios."},

    # 13. Problemas o incidencias
    {"key": "ac_not_working", "q": "No funciona el aire acondicionado, ¿pueden revisarlo?", "a": "Por favor llame a recepción para que podamos revisarlo."},
    {"key": "no_hot_water", "q": "No tengo agua caliente, ¿qué hago?", "a": "Por favor llame a recepción para que podamos asistirle."},
    {"key": "tv_not_working", "q": "No funciona la televisión.", "a": "Por favor llame a recepción para reportar el problema con la televisión."},
    {"key": "no_power_in_room", "q": "No hay luz en mi habitación.", "a": "Por favor llame a recepción para reportar la falta de luz en su habitación."},
    {"key": "remote_not_working", "q": "El control remoto no funciona.", "a": "Por favor llame a recepción para solicitar asistencia o un control de reemplazo."},
    {"key": "noise_problem", "q": "Tengo un problema con el ruido.", "a": "Por favor llame a recepción para que podamos ayudarle con el problema de ruido."},
    {"key": "wifi_down", "q": "Se cayó la conexión del wifi.", "a": "Por favor llame a recepción para reportar el problema de conexión."},
    {"key": "bad_smell", "q": "Hay mal olor en la habitación.", "a": "Por favor llame a recepción para que podamos revisar su habitación."},
    {"key": "key_not_working", "q": "La llave no abre la puerta.", "a": "Por favor llame a recepción o acérquese para revisar su tarjeta y entregarle una nueva."},
    {"key": "bathroom_leak", "q": "Hay una fuga de agua en el baño.", "a": "Por favor llame a recepción para reportar la fuga de agua."},
    {"key": "insect_in_room", "q": "Encontré un insecto o algo extraño en la habitación.", "a": "Por favor llame a recepción para que podamos asistirle."},
    {"key": "minibar_not_cooling", "q": "El minibar no enfría.", "a": "Por favor llame a recepción para reportar el problema del minibar."},
    {"key": "cleaning_not_arrived", "q": "No llega la limpieza que pedí.", "a": "Por favor llame a recepción para que podamos coordinar el servicio de limpieza."},
    {"key": "lost_and_found", "q": "Dejé algo olvidado en el hotel, ¿pueden ayudarme?", "a": "Por favor llame al 233486200 para consultas por objetos olvidados."},
]



# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """
    Normalize text for rough matching:
    - Lowercase
    - Strip accents
    - Remove punctuation except spaces
    - Collapse whitespace
    """
    if not text:
        return ""

    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9ñáéíóúü ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_field(item: Any, field: str, default: str = "") -> str:
    """
    Safely read a field ('key', 'q', 'a') from either:
    - a dict with that key, or
    - a dataclass/obj with that attribute.
    """
    if isinstance(item, Mapping):
        return str(item.get(field, default) or "")
    return str(getattr(item, field, default) or "")


# ---------------------------------------------------------------------------
# Static matching (no LLM)
# ---------------------------------------------------------------------------


def _best_static_match(
    user_text: str,
    faq_items: Iterable[Any],
    min_overlap: float = 0.5,
) -> Optional[Any]:
    """
    Very simple token-overlap matcher between the normalized user text and each FAQ question.

    - Computes overlap = |tokens_user ∩ tokens_question| / |tokens_question|.
    - Returns the FAQ with highest overlap, if >= min_overlap.
    """
    norm_user = _normalize(user_text)
    if not norm_user:
        return None

    user_tokens = set(norm_user.split())
    if not user_tokens:
        return None

    best_item: Optional[Any] = None
    best_score = 0.0

    for item in faq_items:
        q_text = _get_field(item, "q")
        if not q_text:
            continue

        norm_q = _normalize(q_text)
        q_tokens = set(norm_q.split())
        if not q_tokens:
            continue

        overlap = len(user_tokens & q_tokens) / float(len(q_tokens))
        if overlap > best_score:
            best_score = overlap
            best_item = item

    if best_item and best_score >= min_overlap:
        logger.debug(
            "FAQ static match",
            extra={"key": _get_field(best_item, "key"), "score": best_score, "user": user_text},
        )
        return best_item

    return None



# ---------------------------------------------------------------------------
# LLM-based matching as fallback
# ---------------------------------------------------------------------------

_FAQ_SYSTEM_PROMPT = """
You are an FAQ assistant for a hotel WhatsApp bot (Hestia).

You receive:
- A list of FAQs (question + answer).
- A short guest message.

Your job:
1) Decide if the guest message matches one of the existing FAQs.
2) If it matches, answer using ONLY the information in the FAQ list.
3) If it does NOT match any FAQ, answer with exactly: NO_MATCH

Constraints:
- Always answer in the same language as the guest (mostly Spanish).
- Be concise and friendly when answering.
"""


def _call_faq_llm(user_text: str, faq_items: Iterable[Any]) -> Optional[str]:
    """
    Ask the LLM to pick or synthesize an answer from the FAQ list.

    Returns:
        - A short answer as string, or
        - None if the LLM decides there is no relevant FAQ (NO_MATCH or error).
    """
    faq_block_lines = []
    for item in faq_items:
        key = _get_field(item, "key")
        q = _get_field(item, "q")
        a = _get_field(item, "a")
        if not q or not a:
            continue
        faq_block_lines.append(f"- [{key}] Q: {q}\n  A: {a}")
    faq_block = "\n".join(faq_block_lines)

    if not faq_block:
        return None

    try:
        resp = _client.responses.create(
            model=FAQ_LLM_MODEL,
            input=[
                {"role": "system", "content": _FAQ_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"FAQs:\n{faq_block}\n\n"
                        f"Mensaje del huésped:\n{user_text}\n\n"
                        "Responde solo con la respuesta final o NO_MATCH."
                    ),
                },
            ],
            max_output_tokens=256,
        )
        text = resp.output[0].content[0].text.strip()
    except Exception:
        logger.exception("FAQ LLM call failed")
        return None

    if not text or text.upper().startswith("NO_MATCH"):
        return None
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def answer_faq(
    user_text: str,
    faq_items: Optional[Iterable[FAQItem]] = None,
    use_llm_fallback: bool = True,
) -> Optional[str]:
    """
    Try to answer `user_text` using the FAQ list.

    Strategy:
    1) Try static token-overlap matching (fast, deterministic).
    2) If no static match and use_llm_fallback=True, ask the LLM to reason over the FAQ list.

    Returns:
        - The answer text (string) if a relevant FAQ was found.
        - None if no FAQ applies.
    """
    items = list(faq_items) if faq_items is not None else FAQ_ITEMS

    # 1) Static match first
    static_item = _best_static_match(user_text, items)
    if static_item:
        # Works for both dicts and FAQItem dataclasses
        if isinstance(static_item, dict):
            return static_item.get("a")
        return getattr(static_item, "a", None)


    # 2) Optional LLM fallback
    if use_llm_fallback:
        llm_answer = _call_faq_llm(user_text, items)
        return llm_answer

    return None


def has_faq_match(user_text: str, faq_items: Optional[Iterable[FAQItem]] = None) -> bool:
    """
    Convenience helper: returns True if `answer_faq` finds any match.
    """
    return answer_faq(user_text, faq_items=faq_items, use_llm_fallback=False) is not None
