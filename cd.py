# cd.py — розрахунок вартості з включеними 2 км в стартову ціну


def calculate_price(car_class: str, distance_km: float) -> int:
    # Стартова ціна (включає до 2 км)
    pickup_fees = {"Стандарт": 120, "Комфорт": 150, "Бізнес": 180}

    # Ціна за кожен км понад 2 км
    per_km_rates = {"Стандарт": 20, "Комфорт": 25, "Бізнес": 27}

    pickup = pickup_fees.get(car_class, 120)
    per_km = per_km_rates.get(car_class, 20)

    if distance_km <= 2:
        return pickup
    else:
        extra_km = distance_km - 2
        return int(pickup + extra_km * per_km)
