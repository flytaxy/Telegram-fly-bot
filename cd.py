def calculate_price(distance_km, car_class):
    base_prices = {"Стандарт": 100, "Комфорт": 130, "Бізнес": 170}
    per_km_rates = {"Стандарт": 17, "Комфорт": 20, "Бізнес": 24}

    base_price = base_prices[car_class]
    per_km_rate = per_km_rates[car_class]

    if distance_km <= 2:
        price = base_price
    else:
        price = base_price + (distance_km - 2) * per_km_rate

    return round(price)
