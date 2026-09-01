"""Product nouns per taxonomy leaf, and the words a supplier brands with.

Kept apart from the generator itself because it is a word list and nothing
else: no rule reads it, no check depends on it, and the generator would be
twice as long and half as readable with ninety tuples inlined in it.

The nouns are what a shopper would call the thing. They exist so a generated
line reads as a product a person could buy rather than as
``general.garden.tools item 4`` - a reviewer looking at the onboarding queue has
to be able to tell at a glance that Fenwold sent secateurs and Draycott sent a
board game, because that judgement is what the queue is for.

Every key is a leaf in the retailer profile's taxonomy. A leaf with no entry
falls back to the last segment of its display label, which is correct and dull.
"""

from __future__ import annotations

#: Leaf code -> product nouns a supplier in that leaf would actually send.
NOUNS: dict[str, tuple[str, ...]] = {
    # ---- food -------------------------------------------------------------
    "food.alcohol.beer": ("Session IPA", "Amber Ale", "Craft Lager",
                          "Dry Cider"),
    "food.alcohol.spirits": ("London Dry Gin", "Spiced Rum", "Single Malt",
                             "Botanical Vodka"),
    "food.alcohol.wine": ("Malbec Reserve", "Sauvignon Blanc", "Rioja Crianza",
                          "Prosecco Brut"),
    "food.ambient.cereals": ("Bran Flakes", "Malted Wheat Squares",
                             "Honey Nut Clusters", "Porridge Oats"),
    "food.ambient.pasta-rice": ("Fusilli", "Basmati Rice", "Wholewheat Penne",
                                "Arborio Risotto Rice"),
    "food.ambient.sauces": ("Tomato & Basil Sauce", "Korma Cooking Sauce",
                            "Black Bean Stir Fry Sauce", "Sweet Chilli Sauce"),
    "food.bakery.biscuits": ("All Butter Shortbread", "Oat & Raisin Cookies",
                             "Ginger Snaps", "Digestive Biscuits"),
    "food.bakery.bread": ("Wholemeal Batch Loaf", "Sourdough Bloomer",
                          "Seeded Farmhouse Loaf", "Soft White Rolls"),
    "food.bakery.cakes": ("Victoria Sponge", "Lemon Drizzle Loaf",
                          "Bakewell Tart", "Carrot Cake"),
    "food.beverages.coffee": ("Colombian Ground Coffee", "Espresso Beans",
                              "Decaf Instant Coffee", "Breakfast Blend Pods"),
    "food.beverages.juice": ("Orange Juice", "Cloudy Apple Juice",
                             "Sparkling Elderflower", "Cranberry Juice"),
    "food.beverages.tea": ("Everyday Tea Bags", "Earl Grey", "Green Tea",
                           "Peppermint Infusion"),
    "food.chilled.cooked-meats": ("Wiltshire Ham", "Roast Chicken Slices",
                                  "Peppered Salami", "Smoked Turkey Breast"),
    "food.chilled.ready-meals": ("Chicken Tikka Masala", "Lasagne al Forno",
                                 "Cottage Pie", "Thai Green Curry"),
    "food.dairy.cheese": ("Mature Cheddar", "Creamy Brie", "Red Leicester",
                          "Crumbly Wensleydale"),
    "food.dairy.milk": ("Semi Skimmed Milk", "Whole Milk",
                        "Organic Whole Milk", "Lactose Free Milk"),
    "food.dairy.yoghurt": ("Greek Style Yoghurt", "Strawberry Yoghurt",
                           "Natural Yoghurt", "Vanilla Skyr"),
    "food.frozen.desserts": ("Vanilla Ice Cream", "Chocolate Gateau",
                             "Raspberry Sorbet", "Apple Crumble"),
    "food.frozen.vegetables": ("Garden Peas", "Mixed Vegetables",
                               "Sweetcorn", "Chopped Spinach"),
    "food.snacks.bars": ("Trail Mix Bar", "Oat & Honey Bar",
                         "Peanut Protein Bar", "Fruit & Nut Bar"),
    "food.snacks.crisps": ("Lightly Salted Crisps", "Sea Salt & Vinegar Crisps",
                           "Hand Cooked Sharing Crisps", "Cheese Puffs"),
    "food.snacks.granola": ("Granola Clusters", "Berry Granola",
                            "Maple & Pecan Granola", "Toasted Oat Granola"),
    "food.snacks.nuts": ("Salted Cashews", "Roasted Almonds",
                         "Mixed Nuts & Raisins", "Pistachio Kernels"),
    # ---- home -------------------------------------------------------------
    "home.air-treatment.fans": ("Desk Fan", "Tower Fan", "Pedestal Fan",
                                "Bladeless Fan"),
    "home.air-treatment.humidifiers": ("Ultrasonic Humidifier",
                                       "Cool Mist Humidifier",
                                       "Evaporative Humidifier",
                                       "Bedroom Humidifier"),
    "home.air-treatment.purifiers": ("HEPA Air Purifier", "Compact Purifier",
                                     "Large Room Purifier",
                                     "Carbon Filter Purifier"),
    "home.cookware.knives": ("Chef's Knife", "Santoku Knife",
                             "Knife Block Set", "Paring Knife"),
    "home.cookware.pans": ("Non Stick Frying Pan", "Stainless Saucepan Set",
                           "Casserole Dish", "Wok"),
    "home.floorcare.vacuums": ("Cordless Stick Vacuum", "Upright Vacuum",
                               "Cylinder Vacuum", "Robot Vacuum"),
    "home.kitchen.blenders": ("Jug Blender", "Personal Blender",
                              "Hand Blender", "High Speed Blender"),
    "home.kitchen.kettles": ("Rapid Boil Kettle", "Glass Kettle",
                             "Traditional Kettle", "Travel Kettle"),
    "home.kitchen.microwaves": ("Solo Microwave", "Combination Microwave",
                                "Grill Microwave", "Compact Microwave"),
    "home.kitchen.toasters": ("2 Slice Toaster", "4 Slice Toaster",
                              "Long Slot Toaster", "Compact Toaster"),
    "home.laundry.irons": ("Steam Iron", "Garment Steamer",
                           "Steam Generator Iron", "Travel Iron"),
    "home.textiles.bedding": ("Duvet Set", "Brushed Cotton Sheets",
                              "Hollowfibre Duvet", "Pillow Pair"),
    "home.textiles.towels": ("Bath Towel", "Hand Towel Pair",
                             "Egyptian Cotton Bath Sheet", "Face Cloths"),
    # ---- apparel ----------------------------------------------------------
    "apparel.accessories.bags": ("Canvas Tote Bag", "Leather Holdall",
                                 "Cross Body Bag", "Backpack"),
    "apparel.footwear.boots": ("Chelsea Boots", "Walking Boots",
                               "Ankle Boots", "Chukka Boots"),
    "apparel.footwear.trainers": ("Retro Trainers", "Running Trainers",
                                  "Canvas Plimsolls", "Court Trainers"),
    "apparel.kids.sleepwear": ("Kids Pyjama Set", "Fleece Onesie",
                               "Cotton Nightdress", "Sleepsuit"),
    "apparel.kids.tops": ("Kids T-Shirt", "Long Sleeve Top",
                          "Hooded Sweatshirt", "Polo Shirt"),
    "apparel.mens.knitwear": ("Lambswool Jumper", "Cable Knit Cardigan",
                              "Merino Crew Neck", "Quarter Zip Knit"),
    "apparel.mens.outerwear": ("Quilted Jacket", "Waterproof Parka",
                               "Wool Overcoat", "Harrington Jacket"),
    "apparel.mens.shirts": ("Oxford Shirt", "Flannel Check Shirt",
                            "Linen Shirt", "Poplin Dress Shirt"),
    "apparel.womens.denim": ("High Rise Jeans", "Straight Leg Jeans",
                             "Slim Fit Jeans", "Wide Leg Jeans"),
    "apparel.womens.knitwear": ("Roll Neck Jumper", "Boucle Cardigan",
                                "Cashmere Blend Sweater", "Knitted Vest"),
    "apparel.womens.tops": ("Jersey T-Shirt", "Satin Blouse",
                            "Striped Long Sleeve Top", "Linen Shirt"),
    # ---- electronics ------------------------------------------------------
    "electronics.audio.earbuds": ("True Wireless Earbuds",
                                  "Noise Cancelling Earbuds",
                                  "Sport Earbuds", "Compact Earbuds"),
    "electronics.audio.headphones": ("Over Ear Headphones",
                                     "Studio Headphones",
                                     "Wireless Headphones",
                                     "Noise Cancelling Headphones"),
    "electronics.audio.soundbars": ("2.1 Soundbar", "Compact Soundbar",
                                    "Dolby Atmos Soundbar",
                                    "Soundbar with Subwoofer"),
    "electronics.audio.speakers": ("Portable Bluetooth Speaker",
                                   "Waterproof Speaker", "Party Speaker",
                                   "Mini Speaker"),
    "electronics.computing.laptops": ("14 inch Laptop", "Ultrabook",
                                      "Chromebook", "Gaming Laptop"),
    "electronics.computing.tablets": ("10 inch Tablet", "Kids Tablet",
                                      "Pro Tablet", "Compact Tablet"),
    "electronics.mobile.powerbanks": ("10000mAh Power Bank",
                                      "Slim Power Bank",
                                      "Fast Charge Power Bank",
                                      "Solar Power Bank"),
    "electronics.mobile.smartwatches": ("Fitness Smartwatch",
                                        "GPS Smartwatch", "Hybrid Smartwatch",
                                        "Kids Smartwatch"),
    "electronics.personal.cameras": ("Compact Camera", "Action Camera",
                                     "Instant Camera", "Bridge Camera"),
    "electronics.personal.drones": ("Camera Drone", "Beginner Drone",
                                    "Folding Drone", "Racing Drone"),
    "electronics.vision.projectors": ("Portable Projector",
                                      "Home Cinema Projector",
                                      "Mini Projector", "4K Projector"),
    "electronics.vision.televisions": ("43 inch Smart TV", "50 inch 4K TV",
                                       "32 inch HD TV", "65 inch QLED TV"),
    # ---- hpc --------------------------------------------------------------
    "hpc.cleaning.bleach": ("Thick Bleach", "Original Bleach",
                            "Citrus Bleach", "Disinfectant Spray"),
    "hpc.cleaning.dishwashing": ("Washing Up Liquid", "Dishwasher Tablets",
                                 "Rinse Aid", "Dishwasher Salt"),
    "hpc.cleaning.surface": ("Multi Surface Spray", "Kitchen Cleaner",
                             "Bathroom Cleaner", "Glass Cleaner"),
    "hpc.cosmetics.haircare": ("Hair Serum", "Leave In Conditioner",
                               "Curl Cream", "Heat Protect Spray"),
    "hpc.cosmetics.skincare": ("Daily Moisturiser", "Vitamin C Serum",
                               "Night Cream", "Micellar Water"),
    "hpc.laundry.detergent": ("Bio Laundry Liquid", "Non Bio Washing Powder",
                              "Laundry Capsules", "Fabric Conditioner"),
    "hpc.paper.kitchen-roll": ("Kitchen Roll", "Super Absorbent Kitchen Roll",
                               "Recycled Kitchen Roll", "Kitchen Roll Twin Pack"),
    "hpc.toiletries.oralcare": ("Fluoride Toothpaste", "Whitening Toothpaste",
                                "Mouthwash", "Interdental Brushes"),
    "hpc.toiletries.shampoo": ("Everyday Shampoo", "Anti Dandruff Shampoo",
                               "Volumising Shampoo", "Dry Shampoo"),
    "hpc.toiletries.shower": ("Shower Gel", "Body Wash", "Bath Soak",
                              "Exfoliating Shower Scrub"),
    # ---- baby -------------------------------------------------------------
    "baby.feeding.bottles": ("Anti Colic Bottle", "Wide Neck Bottle",
                             "Glass Feeding Bottle", "Teat Twin Pack"),
    "baby.feeding.formula": ("First Infant Milk", "Follow On Milk",
                             "Growing Up Milk", "Hungry Baby Milk"),
    "baby.feeding.weaning": ("Baby Rice", "Fruit Pouch",
                             "Vegetable Puree Pouch", "Toddler Snack Puffs"),
    "baby.nappies.nappies": ("Newborn Nappies", "Nappy Pants",
                             "Night Nappies", "Nappies Jumbo Pack"),
    "baby.nappies.wipes": ("Sensitive Baby Wipes", "Water Wipes",
                           "Fragrance Free Wipes", "Wipes Multipack"),
    "baby.toys.activity": ("Activity Gym", "Shape Sorter",
                           "Stacking Rings", "Activity Cube"),
    "baby.toys.soft": ("Comforter Blanket", "Soft Elephant Toy",
                       "Plush Bunny", "Sensory Soft Book"),
    # ---- health -----------------------------------------------------------
    "health.devices.firstaid": ("First Aid Kit", "Adhesive Plasters",
                                "Crepe Bandage", "Instant Cold Pack"),
    "health.devices.thermometers": ("Digital Thermometer",
                                    "Non Contact Thermometer",
                                    "Ear Thermometer", "Forehead Thermometer"),
    "health.medicines.allergy": ("Antihistamine Tablets", "Hayfever Relief",
                                 "Nasal Spray", "Allergy Eye Drops"),
    "health.medicines.cold-flu": ("Cold & Flu Sachets", "Decongestant Tablets",
                                  "Cough Syrup", "Throat Lozenges"),
    "health.medicines.pain-relief": ("Paracetamol Tablets", "Ibuprofen Tablets",
                                     "Ibuprofen Gel", "Migraine Relief"),
    "health.supplements.minerals": ("Magnesium Tablets", "Iron Tablets",
                                    "Zinc Tablets", "Calcium & Vitamin D"),
    "health.supplements.vitamins": ("Vitamin D3", "Multivitamin Tablets",
                                    "Vitamin C Effervescent", "Vitamin B12"),
    # ---- general ----------------------------------------------------------
    "general.diy.handtools": ("Claw Hammer", "Screwdriver Set",
                              "Adjustable Wrench", "Utility Knife"),
    "general.diy.paint": ("Matt Emulsion", "Satin Wood Paint",
                          "Primer Undercoat", "Masonry Paint"),
    "general.garden.bbq": ("Charcoal Kettle BBQ", "Gas Barbecue",
                           "Portable BBQ", "BBQ Tool Set"),
    "general.garden.tools": ("Bypass Secateurs", "Garden Fork",
                             "Hedge Shears", "Border Spade"),
    "general.pet.accessories": ("Dog Lead", "Pet Bed", "Cat Scratching Post",
                                "Grooming Brush"),
    "general.pet.dogfood": ("Complete Dry Dog Food", "Chicken Dog Food Trays",
                            "Puppy Dry Food", "Senior Dog Food"),
    "general.stationery.paper": ("A4 Copier Paper", "Refill Pad",
                                 "Hardback Notebook", "Sticky Notes"),
    "general.toys.games": ("Family Board Game", "Card Game",
                           "Strategy Board Game", "Quiz Game"),
    "general.toys.outdoor": ("Football Goal Set", "Skipping Rope",
                             "Water Blaster", "Garden Swingball"),
}

#: Descriptive words a supplier puts in a variant name. Drawn on per variant so
#: two rows of one product read as two different things a shopper could pick
#: between, which is what ``product_ref`` grouping is for.
VARIANT_WORDS: tuple[str, ...] = (
    "Standard", "Large Pack", "Twin Pack", "Multipack", "Family Size",
    "Value Pack", "Compact", "Deluxe", "Everyday", "Premium", "Refill",
    "Single", "Starter", "Pro", "Classic", "Mini",
)

#: Countries the catalog's own ``origin.country`` values already use, plus the
#: handful a supplier of this shape would plausibly add. Kept short: a country
#: list is not the point of this data set.
COUNTRIES: tuple[str, ...] = (
    "United Kingdom", "Republic of Ireland", "Italy", "Portugal", "Spain",
    "Germany", "Poland", "Netherlands", "France", "Turkey", "China", "Vietnam",
    "India", "Czechia",
)


def nouns_for(leaf: str, label: str) -> tuple[str, ...]:
    """What a product in this leaf is called.

    Falls back to the last segment of the taxonomy's own display label, which
    is a dull answer and never a wrong one - a leaf added to the profile after
    this file was written still produces a readable line.
    """
    found = NOUNS.get(leaf)
    if found:
        return found
    tail = label.rsplit(">", 1)[-1].strip() or leaf.rsplit(".", 1)[-1]
    return (tail,)
