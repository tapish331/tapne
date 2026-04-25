from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import TypeAlias

from PIL import Image, ImageDraw, ImageFont
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import AccountProfile
from blogs.models import Blog, build_demo_blog_cover_storage_name, build_demo_blog_cover_url
from enrollment.models import EnrollmentRequest
from interactions.models import Comment, DirectMessage, DirectMessageThread
from reviews.models import Review
from social.models import Bookmark, FollowRelation
from trips.models import Trip

User = get_user_model()
DemoFont: TypeAlias = ImageFont.ImageFont | ImageFont.FreeTypeFont


# ── Host personas (12) ────────────────────────────────────────────────────────

HOST_SEEDS = [
    ("demo_priya", "Priya", "Sharma", "demo_priya@tapne.demo", "Mumbai, India",
     "Coastal retreat and wellness host. I've guided 200+ travelers through India's stunning coastlines."),
    ("demo_arjun", "Arjun", "Kapoor", "demo_arjun@tapne.demo", "Delhi, India",
     "Himalayan trek guide with 8 years of high-altitude experience. Safety first, summit second."),
    ("demo_sanika", "Sanika", "Patil", "demo_sanika@tapne.demo", "Pune, India",
     "Culinary travel curator. Every great journey passes through a kitchen."),
    ("demo_rajan", "Rajan", "Mehta", "demo_rajan@tapne.demo", "Bengaluru, India",
     "Road trip and wildlife enthusiast. 180,000+ km on Indian highways with zero regrets."),
    ("demo_kavitha", "Kavitha", "Nair", "demo_kavitha@tapne.demo", "Chennai, India",
     "Heritage and culture guide. I make history feel alive, not like a textbook."),
    ("demo_yusuf", "Yusuf", "Khan", "demo_yusuf@tapne.demo", "Hyderabad, India",
     "Desert adventure specialist and adrenaline sports coordinator since 2016."),
    ("demo_leila", "Leila", "Nazari", "demo_leila@tapne.demo", "Dubai, UAE",
     "Premium luxury travel designer for the discerning modern traveler."),
    ("demo_tao", "Tao", "Chen", "demo_tao@tapne.demo", "Singapore",
     "City food and culture explorer. Singapore is my lab, the world is my classroom."),
    ("demo_amara", "Amara", "Osei", "demo_amara@tapne.demo", "Nairobi, Kenya",
     "East African safari and adventure specialist. The Mara is home."),
    ("demo_elena", "Elena", "Vasquez", "demo_elena@tapne.demo", "Barcelona, Spain",
     "Mediterranean culture, art, and coastal travel host based in Barcelona."),
    ("demo_kiran", "Kiran", "Patel", "demo_kiran@tapne.demo", "London, UK",
     "European city break and heritage specialist operating from London since 2019."),
    ("demo_nisha", "Nisha", "Verma", "demo_nisha@tapne.demo", "Jaipur, India",
     "Rajasthan desert and heritage guide. I grew up in the Pink City's palaces."),
]

# ── Traveler personas (60) ────────────────────────────────────────────────────

TRAVELER_SEEDS = [
    ("demo_rahul_m", "Rahul", "Mehta", "demo_rahul_m@tapne.demo", "Mumbai, India"),
    ("demo_ananya_s", "Ananya", "Singh", "demo_ananya_s@tapne.demo", "Delhi, India"),
    ("demo_vikram_r", "Vikram", "Rao", "demo_vikram_r@tapne.demo", "Bengaluru, India"),
    ("demo_pooja_k", "Pooja", "Kumar", "demo_pooja_k@tapne.demo", "Pune, India"),
    ("demo_aditya_g", "Aditya", "Gupta", "demo_aditya_g@tapne.demo", "Hyderabad, India"),
    ("demo_sneha_p", "Sneha", "Pillai", "demo_sneha_p@tapne.demo", "Chennai, India"),
    ("demo_rohan_j", "Rohan", "Joshi", "demo_rohan_j@tapne.demo", "Kolkata, India"),
    ("demo_meera_d", "Meera", "Desai", "demo_meera_d@tapne.demo", "Ahmedabad, India"),
    ("demo_karthik_n", "Karthik", "Nair", "demo_karthik_n@tapne.demo", "Kochi, India"),
    ("demo_preethi_b", "Preethi", "Bhat", "demo_preethi_b@tapne.demo", "Mangalore, India"),
    ("demo_siddharth_v", "Siddharth", "Verma", "demo_siddharth_v@tapne.demo", "Jaipur, India"),
    ("demo_lakshmi_r", "Lakshmi", "Reddy", "demo_lakshmi_r@tapne.demo", "Vizag, India"),
    ("demo_arjit_c", "Arjit", "Chandra", "demo_arjit_c@tapne.demo", "Bhopal, India"),
    ("demo_divya_t", "Divya", "Thomas", "demo_divya_t@tapne.demo", "Thiruvananthapuram, India"),
    ("demo_nikhil_s", "Nikhil", "Shah", "demo_nikhil_s@tapne.demo", "Surat, India"),
    ("demo_kavya_m", "Kavya", "Menon", "demo_kavya_m@tapne.demo", "Thrissur, India"),
    ("demo_shrey_a", "Shrey", "Agarwal", "demo_shrey_a@tapne.demo", "Lucknow, India"),
    ("demo_tanya_b", "Tanya", "Bansal", "demo_tanya_b@tapne.demo", "Chandigarh, India"),
    ("demo_harsh_p", "Harsh", "Pandey", "demo_harsh_p@tapne.demo", "Varanasi, India"),
    ("demo_ritu_k", "Ritu", "Kapoor", "demo_ritu_k@tapne.demo", "Amritsar, India"),
    ("demo_ajay_w", "Ajay", "Wagh", "demo_ajay_w@tapne.demo", "Nagpur, India"),
    ("demo_suma_r", "Suma", "Rao", "demo_suma_r@tapne.demo", "Mysore, India"),
    ("demo_dhruv_m", "Dhruv", "Mishra", "demo_dhruv_m@tapne.demo", "Patna, India"),
    ("demo_pallavi_g", "Pallavi", "Goel", "demo_pallavi_g@tapne.demo", "Noida, India"),
    ("demo_tushar_n", "Tushar", "Naik", "demo_tushar_n@tapne.demo", "Goa, India"),
    ("demo_sravan_k", "Sravan", "Kumar", "demo_sravan_k@tapne.demo", "Tirupati, India"),
    ("demo_nandita_c", "Nandita", "Chakraborty", "demo_nandita_c@tapne.demo", "Kolkata, India"),
    ("demo_varun_s", "Varun", "Sinha", "demo_varun_s@tapne.demo", "Ranchi, India"),
    ("demo_gayatri_p", "Gayatri", "Prasad", "demo_gayatri_p@tapne.demo", "Hyderabad, India"),
    ("demo_mohit_g", "Mohit", "Gupta", "demo_mohit_g@tapne.demo", "Delhi, India"),
    ("demo_lena_m", "Lena", "Mueller", "demo_lena_m@tapne.demo", "Berlin, Germany"),
    ("demo_james_o", "James", "OBrien", "demo_james_o@tapne.demo", "Dublin, Ireland"),
    ("demo_sofia_l", "Sofia", "Larsson", "demo_sofia_l@tapne.demo", "Stockholm, Sweden"),
    ("demo_carlos_r", "Carlos", "Rivera", "demo_carlos_r@tapne.demo", "Mexico City, Mexico"),
    ("demo_yuki_t", "Yuki", "Tanaka", "demo_yuki_t@tapne.demo", "Tokyo, Japan"),
    ("demo_fatima_a", "Fatima", "AlRashid", "demo_fatima_a@tapne.demo", "Riyadh, Saudi Arabia"),
    ("demo_amelia_w", "Amelia", "Wright", "demo_amelia_w@tapne.demo", "Sydney, Australia"),
    ("demo_chen_x", "Chen", "Xin", "demo_chen_x@tapne.demo", "Shanghai, China"),
    ("demo_ibrahim_k", "Ibrahim", "Kofi", "demo_ibrahim_k@tapne.demo", "Accra, Ghana"),
    ("demo_ana_p", "Ana", "Pereira", "demo_ana_p@tapne.demo", "Lisbon, Portugal"),
    ("demo_raj_s2", "Raj", "Sharma", "demo_raj_s2@tapne.demo", "Shimla, India"),
    ("demo_deepa_v", "Deepa", "Varghese", "demo_deepa_v@tapne.demo", "Kottayam, India"),
    ("demo_vinod_n", "Vinod", "Nambiar", "demo_vinod_n@tapne.demo", "Calicut, India"),
    ("demo_priya_j", "Priya", "Jain", "demo_priya_j@tapne.demo", "Udaipur, India"),
    ("demo_anand_t", "Anand", "Trivedi", "demo_anand_t@tapne.demo", "Indore, India"),
    ("demo_rashmi_s", "Rashmi", "Shukla", "demo_rashmi_s@tapne.demo", "Allahabad, India"),
    ("demo_manoj_p", "Manoj", "Pillai", "demo_manoj_p@tapne.demo", "Trivandrum, India"),
    ("demo_sanjana_b", "Sanjana", "Bose", "demo_sanjana_b@tapne.demo", "Darjeeling, India"),
    ("demo_chirag_d", "Chirag", "Dubey", "demo_chirag_d@tapne.demo", "Raipur, India"),
    ("demo_snehal_k", "Snehal", "Kale", "demo_snehal_k@tapne.demo", "Kolhapur, India"),
    ("demo_vikash_r", "Vikash", "Roy", "demo_vikash_r@tapne.demo", "Guwahati, India"),
    ("demo_aparna_m", "Aparna", "Menon", "demo_aparna_m@tapne.demo", "Palakkad, India"),
    ("demo_suresh_i", "Suresh", "Iyer", "demo_suresh_i@tapne.demo", "Coimbatore, India"),
    ("demo_bhuvan_c", "Bhuvan", "Chawla", "demo_bhuvan_c@tapne.demo", "Ludhiana, India"),
    ("demo_preeti_r", "Preeti", "Rana", "demo_preeti_r@tapne.demo", "Dehradun, India"),
    ("demo_girish_s", "Girish", "Sharma", "demo_girish_s@tapne.demo", "Jodhpur, India"),
    ("demo_sunita_a", "Sunita", "Ahuja", "demo_sunita_a@tapne.demo", "Jalandhar, India"),
    ("demo_akshay_b", "Akshay", "Bhatt", "demo_akshay_b@tapne.demo", "Haridwar, India"),
    ("demo_rekha_g", "Rekha", "Ghosh", "demo_rekha_g@tapne.demo", "Siliguri, India"),
    ("demo_harish_t", "Harish", "Tiwari", "demo_harish_t@tapne.demo", "Banaras, India"),
    ("demo_neetha_v", "Neetha", "Vijay", "demo_neetha_v@tapne.demo", "Madurai, India"),
]

# ── Trip seed data ─────────────────────────────────────────────────────────────
# Tuple: (host, title, trip_type, destination, summary, budget_tier, difficulty,
#         pace, group_size, total_seats, price_per_person, highlights, included,
#         itinerary_day_titles, faqs, duration_days)
# Indices 0-4 → draft; 5-19 → completed; 20-69 → published

TRIP_SEEDS = [
    # ── DRAFT (5) ─────────────────────────────────────────────────────────────
    (
        "demo_priya", "Goa Hidden Beaches & Yoga Retreat", "wellness", "Goa, India",
        "7 days of yoga, meditation, and secret beach exploration away from tourist crowds.",
        "mid", "easy", "relaxed", "6-8 travelers", 8, 18500,
        ["Morning yoga at private beach villa", "Secret beach kayaking", "Goan cuisine workshop", "Sunset meditation at Arambol"],
        ["All meals", "Beachside accommodation", "Yoga instructor", "Kayak rental", "Airport transfers"],
        ["Arrival & Welcome Ceremony", "Yoga & Beach Walk", "Kayaking to Secret Beaches", "Spice Plantation Visit", "Silent Day", "Cooking Class", "Farewell Bonfire"],
        [{"question": "Do I need prior yoga experience?", "answer": "No, all levels welcome."},
         {"question": "Is accommodation private?", "answer": "Yes, exclusive beach villa."}],
        7,
    ),
    (
        "demo_arjun", "Spiti Valley Winter Expedition", "camping", "Spiti Valley, Himachal Pradesh",
        "A raw, unfiltered winter expedition through one of the world's highest inhabited valleys.",
        "mid", "challenging", "fast", "4-6 travelers", 6, 28000,
        ["Kunzum Pass at 4,590m", "Traditional Spitian homestay", "Key Monastery in snow", "Chicham Bridge"],
        ["All accommodation", "Meals during trek", "Local guide", "Emergency oxygen", "Permits"],
        ["Manali & Gear Check", "Drive to Kaza via Kunzum Pass", "Key Monastery & Pin Valley", "Chicham Bridge & Komic Village", "Hikkim Post Office", "Return to Manali"],
        [{"question": "Minimum fitness?", "answer": "Walk 8-12km/day at altitude."},
         {"question": "Is winter camping safe?", "answer": "Yes, -20C rated gear provided."}],
        6,
    ),
    (
        "demo_tao", "Tokyo Ramen & Street Food Deep Dive", "food-culture", "Tokyo, Japan",
        "5 days exploring Tokyo's legendary food scene from Tsukiji to hole-in-the-wall ramen shops.",
        "premium", "easy", "balanced", "6-8 travelers", 8, 35000,
        ["Private Tsukiji morning tour", "Ramen crawl across 4 neighborhoods", "Izakaya dinner with chef", "Teamlab Borderless"],
        ["Hotel 4 nights", "All food included", "Train pass", "English-Japanese guide", "Sake tasting"],
        ["Arrival & Shinjuku Night", "Tsukiji & Shibuya Street Food", "Ramen Neighborhoods", "Asakusa & Izakaya", "Teamlab & Harajuku"],
        [{"question": "Need Japanese?", "answer": "No, guide handles all."},
         {"question": "Dietary restrictions?", "answer": "Vegetarian with advance notice."}],
        5,
    ),
    (
        "demo_leila", "Maldives Premium Island Hopping", "coastal", "Maldives",
        "6 nights across two private island resorts with snorkeling, diving, and sunset cruises.",
        "premium", "easy", "relaxed", "4-6 travelers", 6, 55000,
        ["Water villa on Raa Atoll", "Private sunset dhoni cruise", "Manta ray snorkeling", "Bioluminescent beach"],
        ["Seaplane transfers", "All meals full board", "2 dives/snorkel", "Sunset cruise", "Water sports"],
        ["Arrive Male & Seaplane to Resort 1", "Reef Snorkeling & Spa", "Hanifaru Bay Mantas", "Seaplane to Water Villa", "Diving & Sunset Cruise", "Bioluminescent Beach & Depart"],
        [{"question": "Diving experience needed?", "answer": "No, discover dive available."},
         {"question": "Best time?", "answer": "Nov-Apr best visibility."}],
        6,
    ),
    (
        "demo_elena", "Santorini Sunset & Aegean Escape", "coastal", "Santorini, Greece",
        "5 days on the most iconic Greek island — caldera sunsets, volcanic beaches, and local wine.",
        "premium", "easy", "relaxed", "6-8 travelers", 8, 42000,
        ["Caldera sunset from Oia", "Private catamaran sailing", "Black sand beach Perissa", "Santo Wines tasting"],
        ["Cave hotel 4 nights", "Daily breakfast + 2 dinners", "Catamaran trip", "Wine tasting", "Transfers"],
        ["Arrive Fira & Caldera Walk", "Akrotiri & Red Beach", "Catamaran Day", "Oia & Sunset", "Santo Wines & Depart"],
        [{"question": "Good for solo travelers?", "answer": "Absolutely, warm group dynamic."},
         {"question": "Hikes strenuous?", "answer": "Fira-to-Oia is 10km, easier routes available."}],
        5,
    ),
    # ── COMPLETED (15) ────────────────────────────────────────────────────────
    (
        "demo_arjun", "Kedarnath Trek: Himalayan Pilgrimage", "trekking", "Kedarnath, Uttarakhand",
        "6-day high altitude trek to one of India's most sacred shrines at 3,583m.",
        "mid", "challenging", "balanced", "6-10 travelers", 10, 16500,
        ["Trek through rhododendron forests", "Sonprayag confluence", "Kedarnath temple at dawn", "Panoramic peak views"],
        ["Accommodation tents+guesthouses", "All meals", "Mountain guide", "First aid", "Permits"],
        ["Haridwar & Rishikesh Briefing", "Drive to Sonprayag & Trek", "Trek to Linchaoli", "Summit Kedarnath", "Rest Day", "Return Trek"],
        [{"question": "Altitude?", "answer": "Temple at 3,583m, base 1,829m."},
         {"question": "Helicopter available?", "answer": "HEMS evacuation routes briefed. Helicopter option available."}],
        6,
    ),
    (
        "demo_arjun", "Roopkund Mystery Trek", "trekking", "Roopkund, Uttarakhand",
        "8-day trek to the mysterious skeletal lake at 5,029m. India's most dramatic high-altitude experience.",
        "mid", "challenging", "fast", "6-8 travelers", 8, 22000,
        ["Roopkund skeletal lake", "Bedni and Ali Bugyal meadows", "Junargali panorama", "Rhododendron forest in bloom"],
        ["Full camping equipment", "All meals", "2 guides", "Oxygen emergency cylinders", "Porters"],
        ["Lohajung & Acclimatization", "Didna Village", "Bedni Bugyal", "Pathar Nachauni Camp", "Bhagwabasa High Camp", "Roopkund Summit", "Return to Wan", "Drive Back"],
        [{"question": "Story of Roopkund?", "answer": "500+ skeletons from 9th-century pilgrimage disaster."},
         {"question": "Night temperatures?", "answer": "-10 to -15C at lake. Good sleeping bags essential."}],
        8,
    ),
    (
        "demo_kavitha", "Hampi Ruins & Historical Walk", "culture-heritage", "Hampi, Karnataka",
        "4 days exploring the magnificent ruins of the Vijayanagara Empire across 36 sq km.",
        "budget", "easy", "relaxed", "6-10 travelers", 12, 8500,
        ["Virupaksha Temple sunrise", "Vittala stone chariot", "Elephant stables", "Hemakuta Hill sunset"],
        ["Guesthouse 3 nights", "Breakfast + 2 lunches", "ASI guide", "Bicycle rental", "Coracle ride"],
        ["Arrive Hospete & Settle", "Royal Enclosure & Sacred Centre", "Riverside Ruins & Coracle", "Vittala Temple & Matanga Hill"],
        [{"question": "Suitable for elderly?", "answer": "Electric carts available at major monuments."},
         {"question": "Best season?", "answer": "Oct-Mar. Avoid summer 40C+."}],
        4,
    ),
    (
        "demo_rajan", "Coorg to Ooty Road Trip", "road-trip", "Coorg & Ooty, South India",
        "5-day scenic drive through coffee estates, spice plantations, and Nilgiri Hills.",
        "mid", "easy", "balanced", "4-6 travelers", 6, 12000,
        ["Mist over Abbey Falls", "Coffee plantation walkthrough", "Nilgiri Mountain Railway", "Doddabetta Peak sunrise"],
        ["All accommodation boutique stays", "Breakfasts included", "SUV + driver", "Coffee and tea tastings", "Nilgiri train ticket"],
        ["Bengaluru Pickup & Drive to Coorg", "Coorg Plantation & Abbey Falls", "Raja's Seat & Spice Market", "Drive to Ooty", "Nilgiri Train & Doddabetta"],
        [{"question": "Join from another city?", "answer": "Join at Mysore or Coorg with advance notice."},
         {"question": "Vehicle type?", "answer": "Toyota Innova Crysta or Kia Carens."}],
        5,
    ),
    (
        "demo_sanika", "Mumbai Street Food Safari", "food-culture", "Mumbai, Maharashtra",
        "2-day deep dive into Mumbai's legendary street food culture from Vada Pav to Bhelpuri.",
        "budget", "easy", "fast", "6-10 travelers", 12, 5500,
        ["Vada Pav at Dadar market", "Bhelpuri at Chowpatty Beach", "Midnight biryani Mohammed Ali Road", "Parsi Dhansak at Irani cafe"],
        ["All food tastings 20+ items", "Local guide", "Train pass", "Recipe booklet", "Welcome Chai"],
        ["Morning Dadar & Breakfast Stalls", "Girgaon Chowpatty & Sweets", "Mohammed Ali Road Night Trail"],
        [{"question": "How much food?", "answer": "20-30 items across 2 days, small portions."},
         {"question": "Vegetarian options?", "answer": "70% of trail is vegetarian."}],
        2,
    ),
    (
        "demo_yusuf", "Jaisalmer Desert Safari & Camel Camp", "desert", "Jaisalmer, Rajasthan",
        "3 nights in the Thar Desert — camel ride, dune camp, stargazing, and folk music by firelight.",
        "mid", "easy", "relaxed", "6-10 travelers", 10, 9500,
        ["Camel ride to Sam Sand Dunes at sunset", "Overnight luxury desert camp", "Folk music and fire dance", "Jaisalmer Fort walk"],
        ["Desert camp 2 nights", "All meals", "Camel ride", "Jeep transfers", "Bonfire and folk performance"],
        ["Jaisalmer Fort & Havelis", "Drive to Sam Dunes & Camel Safari", "Desert Camp & Stargazing", "Kuldhara Ghost Village & Return"],
        [{"question": "Is camp luxurious?", "answer": "Swiss tents with beds, attached bathrooms, 24hr electricity."},
         {"question": "Sandstorm plan?", "answer": "Camps designed for wind resistance with indoor backup."}],
        4,
    ),
    (
        "demo_amara", "Masai Mara Safari: Great Migration", "wildlife", "Masai Mara, Kenya",
        "6-day safari during the Great Migration — witness 1.5 million wildebeest cross the Mara River.",
        "premium", "easy", "balanced", "4-6 travelers", 6, 48000,
        ["Mara River wildebeest crossing", "Big Five game drives", "Maasai village visit", "Hot air balloon sunrise"],
        ["Lodge 5 nights", "All meals", "Expert naturalist drives", "Hot air balloon", "Maasai village", "Park fees"],
        ["Nairobi & Flight to Mara", "Big Five Hunt", "Mara River Crossing", "Balloon Morning & Drive", "Maasai Village & Sundowner", "Return Nairobi"],
        [{"question": "Best time for migration?", "answer": "River crossing Jul-Oct. Year-round Big Five sightings."},
         {"question": "Park fees included?", "answer": "All KWNPS levies and conservancy fees included."}],
        6,
    ),
    (
        "demo_kavitha", "Varanasi & Sarnath Spiritual Journey", "culture-heritage", "Varanasi, Uttar Pradesh",
        "4-day immersion into the world's oldest living city — Ganga Aarti, ghats, and Buddha's first sermon site.",
        "budget", "easy", "relaxed", "6-10 travelers", 10, 7500,
        ["Ganga Aarti at Dashashwamedh Ghat", "Dawn boat ride on Ganges", "Sarnath — Buddha's first discourse", "Banaras silk weaving"],
        ["Guesthouse 3 nights", "Daily breakfast", "Cultural guide", "Boat ride", "Sarnath entry"],
        ["Arrive & Evening Ganga Aarti", "Dawn Ganga Boat & Ghats Walk", "Kashi Vishwanath & Silk Workshop", "Sarnath Day Trip & Depart"],
        [{"question": "Safe for solo women?", "answer": "Yes, reputable guesthouses and guided group."},
         {"question": "Must participate in rituals?", "answer": "Everything optional. Always a respectful observer."}],
        4,
    ),
    (
        "demo_nisha", "Jaipur Pink City Heritage Walk", "culture-heritage", "Jaipur, Rajasthan",
        "3 days exploring Jaipur's royal palaces, bazaars, and the world-famous Amber Fort.",
        "budget", "easy", "balanced", "6-10 travelers", 12, 6500,
        ["Amber Fort elephant ride", "Hawa Mahal sunrise", "Jantar Mantar instruments", "Block printing workshop Bagru"],
        ["Heritage guesthouse 2 nights", "Breakfast + 1 dinner", "Licensed guide", "Amber Fort + elephant", "Workshop fee"],
        ["Arrive & City Palace Walk", "Amber Fort & Nahargarh Sunset", "Jantar Mantar Hawa Mahal & Bagru"],
        [{"question": "Ethical elephant ride?", "answer": "Certified welfare-compliant stables, Jaipur Virasat Foundation."},
         {"question": "Shopping time?", "answer": "Free market time each afternoon in Johari Bazaar."}],
        3,
    ),
    (
        "demo_elena", "Barcelona Architecture & Tapas Tour", "city", "Barcelona, Spain",
        "5 days exploring Gaudi's masterpieces, Gothic Quarter, and Barcelona's world-class food scene.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 32000,
        ["Private Sagrada Familia skip-the-line", "Tapas crawl El Born", "Montjuic & Miro Foundation", "FC Barcelona stadium tour"],
        ["Apartment 4 nights", "Daily breakfast", "2 group tapas dinners", "All museum entries", "Metro pass"],
        ["Arrive & Gothic Quarter Walk", "Gaudi Day: Sagrada & Park Guell", "Montjuic & Barceloneta Beach", "El Born Tapas & Camp Nou", "Eixample Architecture & Depart"],
        [{"question": "Barcelona safe?", "answer": "Yes, briefing on pickpocket awareness in tourist areas."},
         {"question": "Need Spanish?", "answer": "No, English widely spoken and guide handles everything."}],
        5,
    ),
    (
        "demo_rajan", "Ranthambore Safari & Jaipur Heritage", "wildlife", "Ranthambore, Rajasthan",
        "5-day combo of tiger safari and Rajputana heritage. India's most photogenic wildlife-culture combo.",
        "mid", "easy", "balanced", "4-6 travelers", 6, 16500,
        ["Open jeep safari zones 1-5", "Tiger spotting from Ranthambore Fort", "Albert Hall Museum", "Khilchipur village interaction"],
        ["Jungle resort 2 nights + heritage hotel 2 nights", "Breakfasts + safari lunches", "Game drive fees", "Jaipur city tour", "Transfers"],
        ["Arrive Sawai Madhopur & Sunset Drive", "Full Day Safari Morning + Evening", "Fort Walk & Drive to Jaipur", "Amber Fort & City Palace", "Departure"],
        [{"question": "Tiger sighting guaranteed?", "answer": "No guarantee, but 75%+ success rate in Ranthambore."},
         {"question": "Camera equipment?", "answer": "200-400mm lens recommended. Rentals available."}],
        5,
    ),
    (
        "demo_tao", "Singapore Street Food & Culture Walk", "food-culture", "Singapore",
        "3-day food and culture deep dive across Singapore's iconic hawker centres and neighborhoods.",
        "mid", "easy", "balanced", "6-10 travelers", 10, 22000,
        ["Maxwell Hawker Centre Chicken Rice", "Little India and Arab Street walk", "Chinatown Heritage Centre", "Night Safari"],
        ["Hotel 2 nights", "All food tastings", "MRT day pass", "Night Safari entry", "Cultural guide"],
        ["Arrive & Chinatown Food Walk", "Little India + Kampong Glam + Hawker Centres", "Gardens by the Bay & Night Safari"],
        [{"question": "Expensive?", "answer": "Excellent value, most costs covered."},
         {"question": "Weather?", "answer": "Hot humid year-round 28-32C."}],
        3,
    ),
    (
        "demo_kiran", "London's Hidden History Walk", "city", "London, United Kingdom",
        "4-day deep dive into London's secret history from Roman Londinium to Sherlock Holmes haunts.",
        "premium", "easy", "balanced", "6-8 travelers", 8, 38000,
        ["Private British Museum Egyptian collection", "Southwark Cathedral & Medieval Borough", "Jack the Ripper walking tour", "Churchill War Rooms"],
        ["Boutique hotel 3 nights", "Daily breakfast", "2 pub dinners", "All museum entries", "Oyster card"],
        ["Arrive & Roman Wall Walk", "British Museum & Covent Garden", "Tower of London + Ripper Night Tour", "Churchill Rooms & Depart"],
        [{"question": "Ripper tour appropriate for all ages?", "answer": "Suitable 16+ with historical context."},
         {"question": "Can I add extra days?", "answer": "Yes, hotel extensions and personalised itinerary available."}],
        4,
    ),
    (
        "demo_yusuf", "Rishikesh White Water Rafting & Adventure", "adventure-sports", "Rishikesh, Uttarakhand",
        "3-day adrenaline pack in India's adventure capital — rafting, bungee, and cliff jumping.",
        "budget", "moderate", "fast", "6-10 travelers", 10, 9000,
        ["16km rafting Class III-IV rapids", "83m bungee at Mohan's", "15m cliff jumping into Ganges", "Ganga beach camping"],
        ["Beach camp 2 nights", "All meals", "Rafting + bungee + cliff jump", "Safety equipment", "Campfire"],
        ["Arrive Rishikesh & Camp Setup", "Rafting Day: 16km Expedition", "Bungee Jump & Cliff Dive Day"],
        [{"question": "Prior rafting needed?", "answer": "No experience needed, full safety briefing."},
         {"question": "Minimum age for bungee?", "answer": "18 years, 110kg maximum."}],
        3,
    ),
    (
        "demo_leila", "Dubai Luxury City Break", "city", "Dubai, UAE",
        "4 days in the world's most extravagant city — Burj Khalifa, gold souk, desert safari, and Michelin dining.",
        "premium", "easy", "balanced", "4-6 travelers", 6, 45000,
        ["Burj Khalifa At the Top", "Traditional dhow creek dinner cruise", "Desert camp with falconry", "Dubai Mall and ski slope"],
        ["5-star hotel 3 nights", "Daily breakfast + 2 dinners", "Luxury vehicle transfers", "Desert safari", "All entries"],
        ["Arrive & Downtown Exploration", "Burj Khalifa + Mall + Dhow Dinner", "Desert Safari & Falconry", "Gold Souk Spice Souk & Depart"],
        [{"question": "Safe for solo women?", "answer": "Yes, very safe. Modest dress in souks recommended."},
         {"question": "Currency?", "answer": "UAE Dirham. INR 100 approx AED 4.3."}],
        4,
    ),
    # ── PUBLISHED (50) ────────────────────────────────────────────────────────
    (
        "demo_arjun", "Kasol & Kheerganga Trek", "trekking", "Kasol, Himachal Pradesh",
        "4-day trek in the Parvati Valley — hot springs, deodar forests, and the hippie village of Kasol.",
        "budget", "moderate", "balanced", "6-10 travelers", 12, 7500,
        ["Kheerganga natural hot spring at 2,950m", "Kasol riverside camping", "Chalal village forest walk", "Parvati River views"],
        ["Tent accommodation", "All meals", "Trek guide", "Entry fees", "Delhi transport"],
        ["Delhi Pickup & Drive to Bhuntar", "Kasol Arrival & Village Walk", "Trek to Kheerganga", "Hot Spring & Return Trek"],
        [{"question": "Safe for beginners?", "answer": "Yes, one of India's most popular beginner treks."},
         {"question": "Night temperature?", "answer": "5-10C in summer, light jacket essential."}],
        4,
    ),
    (
        "demo_priya", "Kerala Backwaters Houseboat Escape", "coastal", "Alleppey, Kerala",
        "3 days on a traditional Kerala kettuvallam through the world's most magical waterway system.",
        "mid", "easy", "relaxed", "4-6 travelers", 6, 14500,
        ["Overnight private houseboat", "Sunset cruise through canals", "Toddy tapping & fishing village", "Kerala Sadhya feast"],
        ["Houseboat 2 nights", "All meals Kerala cuisine", "Nature walk", "Coconut lamp class", "Kochi airport transfer"],
        ["Kochi Arrival & Fort Kochi Walk", "Embark Houseboat & Canal Cruise", "Village Exploration & Sunset Sail"],
        [{"question": "Customize meals?", "answer": "Vegetarian, seafood-free, Jain options pre-arranged."},
         {"question": "Best season?", "answer": "Oct-Mar for pleasant weather."}],
        3,
    ),
    (
        "demo_sanika", "Rajasthani Royal Thali Trail", "food-culture", "Jodhpur & Udaipur",
        "4-day journey through Rajasthan's legendary royal cuisine — dal baati, laal maas, and beyond.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 11500,
        ["Traditional thali at 100-year-old haveli", "Mehrangarh laal maas dinner", "Floating palace tea Lake Pichola", "Udaipur home cooking class"],
        ["Heritage hotel 3 nights", "All meals", "Culinary walk guide", "Cooking class", "Fort entry"],
        ["Arrive Jodhpur & Blue City Walk", "Mehrangarh & Sardar Market Food Trail", "Drive to Udaipur & Lake Pichola", "Cooking Class & Floating Palace Farewell"],
        [{"question": "Is food spicy?", "answer": "Bold but adjustable mild-medium for mixed groups."},
         {"question": "Vegetarian options?", "answer": "80% of Rajasthani cuisine is vegetarian."}],
        4,
    ),
    (
        "demo_rajan", "Ladakh Bike Expedition", "road-trip", "Leh-Ladakh",
        "10-day Royal Enfield expedition through the world's highest motorable roads.",
        "mid", "challenging", "fast", "4-6 travelers", 6, 32000,
        ["Khardung La at 5,359m", "Pangong Tso — 3 Idiots lake", "Nubra Valley Bactrian camels", "Magnetic Hill optical illusion"],
        ["Hotel and homestay", "Breakfasts and dinners", "Royal Enfield Himalayan rental", "Fuel", "Emergency support vehicle"],
        ["Fly to Leh & Acclimatization", "Leh Palace & Shanti Stupa", "Khardung La & Nubra Valley", "Bactrian Camel Ride", "Drive to Pangong", "Pangong Sunrise & Return", "Chang La & Hemis", "Magnetic Hill Ride", "Free Day", "Depart Leh"],
        [{"question": "Need bike license?", "answer": "Yes, valid Indian license with two-wheeler endorsement."},
         {"question": "Never ridden big bike?", "answer": "1-day familiarization day available."}],
        10,
    ),
    (
        "demo_kavitha", "Mahabalipuram & Pondicherry Heritage", "culture-heritage", "Tamil Nadu Coast",
        "3-day coastal heritage drive along the Coromandel Coast — Pallava temples and French colonial charm.",
        "budget", "easy", "balanced", "6-10 travelers", 10, 7000,
        ["Shore Temple at sunrise over Bay of Bengal", "Arjuna's Penance rock carving", "White Town French architecture walk", "Sri Aurobindo Ashram meditation"],
        ["Guesthouse 2 nights", "Breakfast + 1 dinner", "ASI guide", "Monument entries", "Pondicherry promenade walk"],
        ["Chennai & Mahabalipuram Arrival", "Shore Temple Pancha Rathas Rock Carvings", "Drive to Pondicherry & French Quarter"],
        [{"question": "Far from Chennai?", "answer": "3 hours. AC vehicle pickup from Chennai."},
         {"question": "Can I extend to Auroville?", "answer": "Yes, optional Auroville day available."}],
        3,
    ),
    (
        "demo_yusuf", "Rann of Kutch White Desert Festival", "desert", "Rann of Kutch, Gujarat",
        "3 days on the world's largest salt flat — full moon nights, folk music, and vibrant Kutchi crafts.",
        "mid", "easy", "relaxed", "6-10 travelers", 10, 10500,
        ["Full moon night on Great White Rann", "Kala Dungar Black Hill sunset", "Kutchi embroidery craft village", "Flamingoes at Nani Rann"],
        ["Tent City 2 nights", "All meals", "Cultural evening", "Jeep safari to rann", "Craft village visit"],
        ["Bhuj Arrival & Old City Walk", "Rann Utsav Festival & Full Moon Walk", "Kala Dungar & Craft Villages"],
        [{"question": "When is Rann Utsav?", "answer": "Oct-Feb. We time to full moon nights."},
         {"question": "Child-friendly?", "answer": "Yes, flat rann walk and craft villages."}],
        3,
    ),
    (
        "demo_amara", "Serengeti & Ngorongoro Crater Safari", "wildlife", "Tanzania",
        "7-day Tanzania safari circuit — Serengeti plains and the 8th wonder crater floor game drives.",
        "premium", "easy", "balanced", "4-6 travelers", 6, 52000,
        ["Serengeti migration herds", "Ngorongoro Crater big five", "Olduvai Gorge museum", "Maasai village interaction"],
        ["Tented lodge 6 nights", "All meals", "Full-day game drives", "Park and crater fees", "Expert naturalist guide"],
        ["Arusha & Safari Briefing", "Tarangire National Park", "Central Serengeti", "Mara River Migration Zone", "Ndutu Plains Cheetah Territory", "Ngorongoro Crater Full Day", "Olduvai Gorge & Depart"],
        [{"question": "Safe for independent travel?", "answer": "Very safe in managed conservation areas."},
         {"question": "Vaccinations required?", "answer": "Yellow fever mandatory. Malaria prophylaxis strongly recommended."}],
        7,
    ),
    (
        "demo_elena", "Andalusia Culture & Flamenco Journey", "culture-heritage", "Seville & Granada, Spain",
        "6 days in southern Spain — Alhambra, flamenco shows, Seville tapas, and white hill villages.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 28000,
        ["Alhambra Palace at golden hour", "Live tablao flamenco in Triana", "Alcazar Royal Palace gardens", "White villages of Sierra Nevada foothills"],
        ["Boutique hotel 5 nights", "Daily breakfast + 2 dinners", "Alhambra skip-the-line", "Flamenco show tickets", "Granada-Seville transfer"],
        ["Arrive Granada & Albaicin", "Alhambra & Generalife", "Drive to Seville via White Villages", "Alcazar & Tapas Crawl", "Cordoba Mezquita Day Trip", "Depart Seville"],
        [{"question": "Best season?", "answer": "Apr-Jun and Sep-Oct. Avoid Jul-Aug 40C+."},
         {"question": "Solo travelers?", "answer": "Absolutely, 50%+ solo travelers most trips."}],
        6,
    ),
    (
        "demo_kiran", "Edinburgh Highland & City Break", "city", "Edinburgh, Scotland",
        "4-day exploration of Scotland's dramatic capital and a day trip into the legendary Highlands.",
        "premium", "easy", "balanced", "6-8 travelers", 8, 36000,
        ["Edinburgh Castle crown jewels", "Loch Ness and Urquhart Castle", "Arthur's Seat sunrise hike", "Royal Mile Scotch whisky tasting"],
        ["Boutique hotel 3 nights", "Daily breakfast + 1 dinner", "All entry tickets", "Highland day trip", "Whisky tasting"],
        ["Arrive & Royal Mile Walk", "Edinburgh Castle & Holyrood Palace", "Highlands: Glencoe & Loch Ness", "Arthur's Seat Hike & Depart"],
        [{"question": "Scotland cold?", "answer": "Summer 15-18C. Layered packing key."},
         {"question": "Loch Ness monster sighting?", "answer": "Always on agenda. Success rate extremely low, fun rate extremely high."}],
        4,
    ),
    (
        "demo_nisha", "Rajasthan Desert & Heritage Circuit", "desert", "Jodhpur Jaisalmer Bikaner",
        "7-day circuit through three fortress cities of Rajasthan and the vast Thar Desert.",
        "mid", "easy", "balanced", "6-10 travelers", 10, 18000,
        ["Mehrangarh Fort — India's most majestic citadel", "Jaisalmer golden sandstone at dusk", "Bikaner Junagarh Fort", "Sam Sand Dunes luxury camp"],
        ["Heritage hotel 6 nights", "Breakfast + 3 dinners", "Guided fort tours", "Desert camp with meals", "AC vehicle throughout"],
        ["Arrive Jodhpur & Blue City Walk", "Mehrangarh Fort & Sardar Market", "Drive to Jaisalmer via Osian", "Jaisalmer Fort & Havelis", "Sam Dunes & Desert Camp", "Bikaner Camel Farm", "Junagarh Fort & Depart"],
        [{"question": "Suitable for senior travelers?", "answer": "Yes, vehicle access to all monuments."},
         {"question": "Self-paced?", "answer": "Free afternoons at each city for shopping."}],
        7,
    ),
    (
        "demo_priya", "Andaman Island Snorkeling & Beaches", "coastal", "Andaman Islands",
        "5 days on India's most pristine islands — Radhanagar Beach, Havelock, and vibrant coral reefs.",
        "mid", "easy", "relaxed", "6-8 travelers", 8, 19500,
        ["Radhanagar Beach — Asia's best beach", "Elephant Beach snorkeling over coral", "Glass-bottom boat Neil Island", "Cellular Jail sound-and-light"],
        ["Guesthouse 4 nights", "Breakfast + 3 dinners", "All ferry transfers", "Snorkeling gear", "Cellular Jail tour"],
        ["Port Blair & Cellular Jail", "Ferry to Havelock Island", "Elephant Beach & Radhanagar", "Ferry to Neil Island & Glass Boat", "Return Port Blair & Depart"],
        [{"question": "Scuba diving available?", "answer": "Yes, PADI instructor for discover scuba at extra cost."},
         {"question": "Best time?", "answer": "Oct-May. Monsoon Jun-Sep restricted boat services."}],
        5,
    ),
    (
        "demo_arjun", "Valley of Flowers Trek", "trekking", "Valley of Flowers, Uttarakhand",
        "6-day UNESCO World Heritage trek through high alpine valley blooming with rare Himalayan flora.",
        "mid", "moderate", "balanced", "6-10 travelers", 10, 15500,
        ["Valley of Flowers in full bloom Jul-Sep", "Hemkund Sahib Gurudwara at 4,329m", "Ghangaria base camp views", "Rare medicinal plants tour with botanist"],
        ["Guesthouse and tent", "All meals", "Guide + botanist", "Forest permits", "Govindghat bus transfer"],
        ["Haridwar Pickup & Drive to Govindghat", "Trek to Ghangaria Base", "Valley of Flowers Exploration", "Hemkund Sahib Optional Trek", "Return Trek to Govindghat", "Return to Haridwar"],
        [{"question": "When do flowers bloom?", "answer": "Peak mid-July to mid-August, open until October."},
         {"question": "Hemkund Sahib mandatory?", "answer": "No, optional 6km/1,400m elevation gain."}],
        6,
    ),
    (
        "demo_kavitha", "Mysore Palace & Coorg Cultural Circuit", "culture-heritage", "Mysore & Coorg",
        "4-day cultural and nature combo through Karnataka's royal city and coffee hill station.",
        "mid", "easy", "relaxed", "6-10 travelers", 10, 10000,
        ["Mysore Palace illumination Sunday evenings", "Chamundi Hill and Nandi Bull shrine", "Coorg Tibetan golden temple", "Kodagu homecooked pork curry"],
        ["Heritage hotel Mysore + plantation homestay Coorg", "All meals", "Cultural guide Mysore", "Coffee plantation walk", "Transfers"],
        ["Arrive Mysore & Palace Walk", "Chamundi Hill & Sunday Illumination", "Drive to Coorg & Plantation Tour", "Abbey Falls Raja's Seat & Depart"],
        [{"question": "Palace open daily?", "answer": "Yes 10am-5:30pm. Sunday illumination 7-7:45pm."},
         {"question": "Non-coffee alternatives?", "answer": "Cardamom, pepper, vanilla plantations equally interesting."}],
        4,
    ),
    (
        "demo_yusuf", "Paragliding & Adventure in Bir Billing", "adventure-sports", "Bir Billing, Himachal Pradesh",
        "4 days in the paragliding capital of India — tandem flights, trekking, and mountain camping.",
        "mid", "moderate", "fast", "6-10 travelers", 10, 13500,
        ["Tandem paragliding with BHPA-certified pilot", "Billing launch site at 2,400m", "Upper Bir monastery trail", "Camping with Dhauladhar sunset"],
        ["Camping 3 nights", "All meals", "Tandem paragliding + certified pilot", "Trek guide", "Dharamshala transport"],
        ["Arrive Dharamshala & Drive to Bir", "Upper Bir Trek & Landing Zone Walk", "Paragliding Day at Billing", "Monastery Trail & Depart"],
        [{"question": "Safe for first-timers?", "answer": "Yes, BHPA certified pilot with 1,000+ flight hours."},
         {"question": "Minimum weight?", "answer": "30kg minimum, 100kg maximum for tandem."}],
        4,
    ),
    (
        "demo_amara", "Mount Kenya Trekking & Wildlife Camp", "camping", "Mount Kenya National Park",
        "6-day circuit around Africa's second-highest mountain — wildlife, glaciers, and alpine camping.",
        "mid", "challenging", "balanced", "4-6 travelers", 6, 38000,
        ["Lenana Summit at 4,985m non-technical", "Alpine moorland with giant lobelias", "Buffalo and elephant in forest zone", "Glacier views from Shipton's Camp"],
        ["Mountain hut and tent", "All meals with cook", "Certified mountain guide", "Park fees", "Nairobi-Mountain Gate transfer"],
        ["Nairobi & Sirimon Gate", "Forest Zone Wildlife", "Moorland Zone to Shipton's Camp", "Summit: Lenana Peak", "Descent to Chogoria Gate", "Nairobi Return"],
        [{"question": "Technical climbing needed?", "answer": "No ropes needed, very good fitness required."},
         {"question": "What wildlife?", "answer": "Buffalo, elephant, hyena, 100+ bird species."}],
        6,
    ),
    (
        "demo_nisha", "Pushkar Camel Fair & Holy Town", "culture-heritage", "Pushkar, Rajasthan",
        "3-day immersion in one of India's most surreal festivals — 50,000 camels and Brahma temple.",
        "budget", "easy", "relaxed", "6-10 travelers", 12, 7000,
        ["Pushkar Camel Fair ground sunrise", "World's only Brahma temple darshan", "Holy lake ghats and aarti", "Camel racing and folk performers"],
        ["Guesthouse 2 nights", "Breakfast + 1 dinner", "Camel Fair entry", "Festival guide", "Auto transfers"],
        ["Arrive Pushkar & Lake Walk", "Camel Fair Ground Full Day", "Brahma Temple & Depart"],
        [{"question": "When is Pushkar Camel Fair?", "answer": "Oct-Nov, Kartik Purnima. Timed to peak fair days."},
         {"question": "Crowded?", "answer": "200,000+ visitors at peak. Arrive early each morning."}],
        3,
    ),
    (
        "demo_rajan", "Jim Corbett Jungle Camp & Wildlife", "camping", "Jim Corbett National Park",
        "3 nights deep in India's oldest national park — tiger territory, river camping, and safari drives.",
        "mid", "easy", "balanced", "4-6 travelers", 6, 13000,
        ["Jeep safari in Bijrani and Dhikala zones", "Elephant-back safari", "Corbett museum naturalist lecture", "Ramganga River walk at dawn"],
        ["Forest camp 3 nights", "All meals", "Safari fees + guide", "Elephant safari fee", "Delhi transport"],
        ["Arrive Corbett & Camp Setup", "Morning Jeep Safari & Bird Walk", "Dhikala Zone Full Day", "Elephant Safari & Depart"],
        [{"question": "Tiger sighting at Corbett?", "answer": "250+ tigers, morning Dhikala drives best odds."},
         {"question": "Inside the forest?", "answer": "Yes, eco-camps inside buffer zone 1km from core boundary."}],
        4,
    ),
    (
        "demo_tao", "Bangkok Food & Night Markets", "food-culture", "Bangkok, Thailand",
        "4 days in Bangkok's legendary food city — night bazaars, street stalls, and floating market.",
        "budget", "easy", "fast", "6-10 travelers", 12, 12000,
        ["Damnoen Saduak Floating Market at dawn", "Chatuchak Market food stalls", "Chinatown Yaowarat Night Street", "Cooking class with Thai chef"],
        ["Guesthouse 3 nights", "All food tastings", "BTS day passes", "Cooking class + market tour", "Floating market day trip"],
        ["Arrive Bangkok & Khao San Night Walk", "Floating Market & Temple Hopping", "Chatuchak & Chinatown Night Trail", "Thai Cooking Class & Depart"],
        [{"question": "Street food safe?", "answer": "High turnover stalls selected. Zero group illness incidents."},
         {"question": "Vegetarian options?", "answer": "Bangkok very vegetarian-friendly."}],
        4,
    ),
    (
        "demo_leila", "Abu Dhabi Cultural & Heritage Tour", "culture-heritage", "Abu Dhabi, UAE",
        "3 days exploring UAE capital's extraordinary culture — Sheikh Zayed Mosque, Louvre, and desert.",
        "premium", "easy", "relaxed", "4-6 travelers", 6, 35000,
        ["Sheikh Zayed Grand Mosque at golden hour", "Louvre Abu Dhabi masterpiece gallery", "Qasr Al Hosn oldest stone building", "Liwa Oasis Moreeb Dune drive"],
        ["5-star hotel 2 nights", "Daily breakfast + 1 dinner", "All entry tickets", "Luxury vehicle", "Liwa desert half-day"],
        ["Arrive Abu Dhabi & Sheikh Zayed Mosque", "Louvre + Saadiyat Cultural District", "Liwa Oasis & Depart"],
        [{"question": "Dress code for mosque?", "answer": "Full modest dress required. Abayas provided free."},
         {"question": "Worth separate trip from Dubai?", "answer": "Absolutely, calmer and more culturally distinct."}],
        3,
    ),
    (
        "demo_elena", "Amalfi Coast Road Trip", "road-trip", "Amalfi Coast, Italy",
        "5-day scenic road trip along Italy's most dramatic coastline — Positano, Ravello, and Capri.",
        "premium", "moderate", "balanced", "4-6 travelers", 6, 40000,
        ["Positano cliffside village", "Ravello Concert Hall with ocean backdrop", "Blue Grotto boat trip Capri", "Limoncello tasting Sorrento"],
        ["Boutique hotel 4 nights", "Daily breakfast + 1 dinner", "Private minibus for coast", "Capri ferry + Blue Grotto", "Ravello music venue"],
        ["Arrive Naples & Drive to Positano", "Positano to Praiano Coastal Walk", "Ravello & Atrani Village", "Capri Island Day Trip", "Sorrento & Return Naples"],
        [{"question": "Is Amalfi road safe?", "answer": "Local driver handles all cliff road driving."},
         {"question": "Capri expensive?", "answer": "Yes, budget INR 3,000 extra for Capri meals."}],
        5,
    ),
    (
        "demo_kiran", "Amsterdam Art & Canal Weekend", "city", "Amsterdam, Netherlands",
        "3-day Amsterdam break — world-class museums, canal house tours, and cycling the city.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 28000,
        ["Rijksmuseum Rembrandt and Vermeer", "Van Gogh Museum priority entry", "Canal boat architecture tour", "Jordaan vintage market walk"],
        ["Boutique hotel 2 nights", "Daily breakfast", "All museum tickets", "Canal boat tour", "City bike rental 2 days"],
        ["Arrive & Canal Walk", "Rijksmuseum + Van Gogh + Heineken Tour", "Jordaan Market + Cycle Tour & Depart"],
        [{"question": "Cycling safe?", "answer": "Cycling primary mode, separate bike lanes from traffic."},
         {"question": "Anne Frank House included?", "answer": "Sells out 8 weeks ahead. We help book in advance."}],
        3,
    ),
    (
        "demo_amara", "Rwanda Gorilla Trekking & Volcanoes", "wildlife", "Volcanoes National Park, Rwanda",
        "4 days tracking endangered mountain gorillas in the Virunga volcanoes of Central Africa.",
        "premium", "challenging", "balanced", "4-6 travelers", 4, 58000,
        ["One hour with gorilla family at 2,500m", "Kigali Genocide Memorial", "Golden monkey tracking in bamboo forest", "Bisoke Volcano crater hike option"],
        ["Luxury eco-lodge 3 nights", "All meals", "Gorilla permit $1,500 included", "Expert ranger guides", "Kigali transfers"],
        ["Arrive Kigali & Genocide Memorial", "Gorilla Trekking Volcanoes NP", "Golden Monkey Trek & Village Walk", "Optional Bisoke Hike & Depart"],
        [{"question": "How difficult is gorilla trek?", "answer": "2-8 hours dense jungle at altitude. Good fitness required."},
         {"question": "Permit included?", "answer": "Yes, full $1,500 RDB permit included."}],
        4,
    ),
    (
        "demo_yusuf", "Pangong Lake & Leh Motorcycle Ride", "adventure-sports", "Leh & Pangong, Ladakh",
        "6-day Ladakh adventure — high-altitude motorcycle ride to the famous blue lake.",
        "mid", "challenging", "fast", "4-6 travelers", 6, 24000,
        ["Pangong Tso at dawn", "Chang La pass at 5,360m", "Nubra Valley with Bactrian camels", "Magnetic Hill optical illusion"],
        ["Hotel and homestay 5 nights", "Breakfast and dinner", "Royal Enfield Himalayan rental", "Fuel", "Emergency support vehicle + mechanic"],
        ["Leh Arrival & Acclimatization", "Leh Local Shanti Stupa Markets", "Khardung La & Nubra Valley", "Nubra Camp & Camel Ride", "Drive to Pangong", "Pangong Sunrise & Return"],
        [{"question": "Breakdown plan?", "answer": "Support vehicle with mechanic follows group all days."},
         {"question": "Altitude?", "answer": "Leh 3,524m. Passes reach 5,360m. Two acclimatization days mandatory."}],
        6,
    ),
    (
        "demo_arjun", "Chopta Chandrashila Winter Trek", "trekking", "Chopta, Uttarakhand",
        "4-day winter trek to pristine Chandrashila summit with views of Nanda Devi and Trishul.",
        "mid", "moderate", "balanced", "6-10 travelers", 10, 10500,
        ["Chandrashila summit at 4,090m", "360-degree panorama Nanda Devi Trishul Chaukhamba", "Tungnath world's highest Shiva temple", "Snow camping at Chopta meadow"],
        ["Tent 3 nights", "All meals", "Mountain guide", "Snow gear rental", "Rishikesh transport"],
        ["Rishikesh Pickup & Drive to Chopta", "Trek to Tungnath & Chandrashila Summit", "Snow Day & Camp", "Return Trek & Rishikesh Depart"],
        [{"question": "Winter trekking safe?", "answer": "Yes with -15C sleeping bags, crampons, snow gaiters."},
         {"question": "Temple open in winter?", "answer": "Closes Nov-Apr. Frozen trail and snow views compensate."}],
        4,
    ),
    (
        "demo_priya", "Coorg Coffee Plantation Wellness Stay", "wellness", "Coorg, Karnataka",
        "3 days of deep relaxation on a working coffee estate — Ayurveda, plantation walks, and mountain air.",
        "mid", "easy", "relaxed", "4-6 travelers", 6, 13000,
        ["Sunrise yoga in coffee estate", "Ayurvedic oil massage at on-site spa", "Coffee cherry picking and processing", "Evening bonfire with filter coffee"],
        ["Plantation cottage 2 nights", "All organic meals", "Yoga and Ayurvedic session", "Coffee tour", "Mysore transfers"],
        ["Arrive Coorg & Sunset Plantation Walk", "Coffee Tour & Ayurvedic Wellness Day", "Yoga Morning & Depart"],
        [{"question": "Prior yoga experience?", "answer": "No, morning yoga gentle for all levels."},
         {"question": "Coffee varieties grown?", "answer": "Arabica, Robusta, and rare Monsooned Malabar."}],
        3,
    ),
    (
        "demo_rajan", "Sundarbans Mangrove Delta", "wildlife", "Sundarbans, West Bengal",
        "3 days deep in the world's largest mangrove delta — Royal Bengal Tiger territory and river life.",
        "mid", "easy", "balanced", "4-6 travelers", 8, 12000,
        ["Tiger tracking boat ride in core zone", "Wild honey collection with Moual hunters", "Sajnekhali Bird Sanctuary birding", "Sunset on Matla River"],
        ["Eco-lodge 2 nights", "All meals Bengali fish curry", "Guided boat safari", "Watchtower access", "Kolkata transfer"],
        ["Kolkata Departure & Sundarbans Entry", "Core Zone Boat Safari & Bird Sanctuary", "Honey Hunters Trail & Return to Kolkata"],
        [{"question": "Tiger sighting likely?", "answer": "10% chance but paw prints and territorial marks common."},
         {"question": "Mosquitoes?", "answer": "Yes. Repellent and nets provided."}],
        3,
    ),
    (
        "demo_sanika", "Onam Feast in Kerala", "food-culture", "Thrissur & Palakkad, Kerala",
        "3-day cultural food journey during Kerala's harvest festival — 26-dish Sadhya and snake boat races.",
        "mid", "easy", "relaxed", "6-10 travelers", 10, 9000,
        ["Traditional Onam Sadhya on banana leaf 26 dishes", "Vallamkali snake boat race at Aranmula", "Pookalam flower carpet workshop", "Thiruvathirakali dance performance"],
        ["Heritage homestay 2 nights", "All meals", "Boat race viewing spot", "Pookalam workshop", "Cultural guide"],
        ["Arrive Thrissur & Onam Procession Walk", "Aranmula Boat Race & Riverside Feast", "Pookalam Workshop & Depart"],
        [{"question": "When is Onam?", "answer": "Aug-Sep, timed to Thiruonam main feast day."},
         {"question": "Is Sadhya all vegetarian?", "answer": "Yes, 100% vegetarian 26 dishes on banana leaf."}],
        3,
    ),
    (
        "demo_nisha", "Shekhawati Painted Haveli Circuit", "culture-heritage", "Shekhawati, Rajasthan",
        "3-day open-air museum tour through Mandawa, Nawalgarh, and Fatehpur — India's fresco capital.",
        "budget", "easy", "relaxed", "6-10 travelers", 10, 7500,
        ["Mandawa Fort frescoes 19th-century painted havelis", "Nawalgarh Poddar Haveli Museum", "Fatehpur Nadine Le Prince cultural centre", "Bullock cart through fresco village lanes"],
        ["Heritage guesthouse 2 nights", "Breakfast + 1 dinner", "Fresco art guide", "Nawalgarh Poddar entry", "Bullock cart experience"],
        ["Arrive Mandawa & Fort Walk", "Nawalgarh Haveli Circuit", "Fatehpur & Depart"],
        [{"question": "Havelis still privately owned?", "answer": "Many yes. Families allow visitors into certain rooms."},
         {"question": "Photography allowed?", "answer": "Outside yes. Inside requires owner permission guide facilitates."}],
        3,
    ),
    (
        "demo_kiran", "Irish Countryside & Cliffs of Moher", "road-trip", "Ireland",
        "5-day road trip through Ireland's wild Atlantic coast — Cliffs of Moher, Connemara, and peat bogs.",
        "premium", "easy", "balanced", "4-6 travelers", 6, 38000,
        ["Cliffs of Moher at dawn 214m Atlantic drop", "Connemara National Park lake walk", "Kylemore Abbey Gothic castle reflection", "Traditional Irish pub session Galway"],
        ["B&B 4 nights", "Daily breakfast", "Private vehicle + driver", "All national park entries", "Aran Islands ferry"],
        ["Arrive Dublin & Wicklow Day", "Drive West Burren & Cliffs of Moher", "Connemara & Kylemore Abbey", "Aran Islands Ferry Day", "Galway Pub Night & Dublin Depart"],
        [{"question": "Driving in Ireland difficult?", "answer": "Left-hand driving on narrow roads. Our driver handles everything."},
         {"question": "Ireland weather?", "answer": "Expect rain any time. Pack waterproofs. Moody weather is the magic."}],
        5,
    ),
    (
        "demo_amara", "Kilimanjaro Summit Attempt", "trekking", "Kilimanjaro, Tanzania",
        "8-day Machame Route attempt on Africa's highest peak — 5,895m summit.",
        "premium", "challenging", "balanced", "4-6 travelers", 6, 65000,
        ["Uhuru Peak summit at 5,895m 78% success rate on Machame", "5 distinct ecological zones", "Barranco Wall scramble", "Sunrise from Stella Point crater rim"],
        ["Mountain hut and tent", "All meals with mountain cook", "Lead guide + 2 assistants + porters", "Park fees and rescue fund", "Moshi airport transfers"],
        ["Arrive Moshi & Gear Check", "Machame Gate to Machame Camp", "Shira Plateau Camp", "Barranco Camp & Wall Scramble", "Karanga & Barafu High Camp", "Summit Night Uhuru Peak", "Descent to Mweka Gate", "Debrief & Depart"],
        [{"question": "Summit success rate?", "answer": "78% on Machame 8-day schedule. We never rush acclimatization."},
         {"question": "Guide certifications?", "answer": "All lead guides KPAP certified and TANAPA licensed."}],
        8,
    ),
    (
        "demo_elena", "Algarve Coastal & Surfing Retreat", "coastal", "Algarve, Portugal",
        "5 days on Europe's most dramatic coastline — sea caves, surfing lessons, and fresh seafood.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 26000,
        ["Kayaking into Benagil Sea Cave", "Beginner surf lesson at Sagres", "Ponta de Sagres edge of the world", "Sunset at Praia da Marinha"],
        ["Surf guesthouse 4 nights", "Daily breakfast + 2 dinners", "2 surf lessons certified instructor", "Kayak and cave tour", "Cape St Vincent day trip"],
        ["Arrive Faro & Tavira Walk", "Benagil Sea Cave Kayak", "Lagos Sea Stack Coastline Walk", "Sagres Surf Lessons", "Cape St Vincent & Depart"],
        [{"question": "Need surfing experience?", "answer": "No, lessons for complete beginners. Most stand by lesson 2."},
         {"question": "Crowded in summer?", "answer": "Jul-Aug peak. Apr-Jun or Sep-Oct better."}],
        5,
    ),
    (
        "demo_rajan", "Kabini Wildlife Wilderness", "wildlife", "Kabini, Karnataka",
        "3 nights at one of South India's premier wildlife reserves — elephant herds, leopard, and Kabini River.",
        "premium", "easy", "relaxed", "4-6 travelers", 6, 22000,
        ["Elephant herd congregation at Kabini River", "Leopard tracking with naturalist", "Morning boat ride across reservoir", "Night trail walk with forest guard"],
        ["Luxury eco-resort 3 nights", "All meals", "Jeep and boat safaris", "Naturalist-guided drives", "Bangalore transfer"],
        ["Arrive Kabini & Evening Boat Safari", "Morning Jeep Safari", "Forest Walk & Afternoon Drive", "Depart"],
        [{"question": "Kabini vs Bandipur?", "answer": "Kabini better for leopard and elephant. Recommend Kabini for first-timers."},
         {"question": "Safari times?", "answer": "Morning 6am, afternoon 4pm, night trail 9pm optional."}],
        4,
    ),
    (
        "demo_leila", "Bali Premium Wellness & Culture", "wellness", "Bali, Indonesia",
        "7 days of Balinese healing, temple rituals, and beach wellness in the island of the gods.",
        "premium", "easy", "relaxed", "4-6 travelers", 6, 38000,
        ["Tirta Empul holy spring purification ceremony", "Ubud yoga and meditation at sunrise", "Mount Batur volcano sunrise hike", "Jimbaran Bay sunset seafood dinner"],
        ["Private pool villa 6 nights", "Daily breakfast + 3 dinners", "Temple ceremonies + guides", "Mount Batur trek", "Transfers throughout Bali"],
        ["Arrive Bali & Seminyak Beach", "Ubud Monkey Forest & Rice Terraces", "Tirta Empul Temple & Wellness", "Mount Batur Sunrise Trek", "Kecak Fire Dance & Tanah Lot", "Jimbaran Bay Seafood Dinner", "Spa Day & Depart"],
        [{"question": "Tirta Empul open to tourists?", "answer": "Yes, all welcome. Sarongs provided."},
         {"question": "Mount Batur difficult?", "answer": "2-hour pre-dawn hike, moderately challenging."}],
        7,
    ),
    (
        "demo_tao", "Ho Chi Minh City Food Trail", "food-culture", "Ho Chi Minh City, Vietnam",
        "3 days eating through Saigon's legendary street food — Pho, Banh Mi, and hidden family kitchens.",
        "budget", "easy", "fast", "6-10 travelers", 12, 9000,
        ["Pho at 5am hole-in-the-wall Ben Thanh", "Banh Mi No 37 Anthony Bourdain's favorite", "Cu Chi tunnels food and history combo", "Ben Thanh night market crawl"],
        ["Guesthouse 2 nights", "All food tastings", "Cu Chi tunnels day trip", "Motorbike taxi food tour", "City guide"],
        ["Arrive HCMC & Night Market Walk", "Pho Sunrise & Temple District Trail", "Cu Chi Tunnels & Ben Thanh Night Market"],
        [{"question": "Safe to eat street food?", "answer": "High turnover stalls. 3 years zero food illness incidents."},
         {"question": "Vegetarian options?", "answer": "Excellent com chay vegetarian rice dishes."}],
        3,
    ),
    (
        "demo_nisha", "Ranthambore & Bharatpur Wildlife Circuit", "wildlife", "Rajasthan Wildlife Corridor",
        "5-day circuit pairing India's best tiger park with the world's finest birding wetland.",
        "mid", "easy", "balanced", "4-6 travelers", 6, 17500,
        ["Ranthambore Zone 3 tiger territory", "Bharatpur Keoladeo rickshaw birding", "Ranthambore Fort ruins inside tiger reserve", "600+ bird species in Bharatpur World Heritage Site"],
        ["Jungle resort + heritage hotel 4 nights", "All meals", "Safari + Bharatpur rickshaw guide", "Jeep rental", "Jaipur transfer"],
        ["Arrive Sawai Madhopur & Evening Drive", "Morning & Afternoon Safaris", "Ranthambore Fort Walk", "Drive to Bharatpur & Bird Sanctuary", "Bharatpur Full Day & Depart"],
        [{"question": "Bharatpur good in summer?", "answer": "Winter Nov-Feb peak for migratory birds. Summer still 200+ residents."},
         {"question": "Can I walk in Bharatpur?", "answer": "Yes, unique park where you can walk, cycle, or rickshaw."}],
        5,
    ),
    (
        "demo_priya", "Lakshadweep Coral Island Retreat", "coastal", "Lakshadweep Islands",
        "5 days on India's last unspoiled coral atoll — crystal lagoons, sea turtles, and zero crowds.",
        "premium", "easy", "relaxed", "4-6 travelers", 6, 35000,
        ["Agatti Island lagoon kayaking over coral", "Sea turtle nesting site at dawn", "Glass-bottom boat Bangaram Atoll", "Unplugged island living no cars no city noise"],
        ["Island resort 4 nights", "All meals fresh seafood", "Kayak and snorkeling gear", "Boat transfers", "Delhi-Kochi-Agatti flight coordination"],
        ["Fly to Agatti & Lagoon Arrival", "Coral Reef Snorkeling & Sunset Kayak", "Bangaram Atoll Glass Boat & Dive", "Sea Turtle Beach & Island Walk", "Depart"],
        [{"question": "How to get to Lakshadweep?", "answer": "Fly Kochi then 90 min flight to Agatti. We coordinate connections."},
         {"question": "Entry permit required?", "answer": "Yes. We handle all documentation."}],
        5,
    ),
    (
        "demo_arjun", "Dzukou Valley Trek & Nagaland Culture", "trekking", "Dzukou Valley, Nagaland",
        "5-day trek to the Valley of Flowers of the Northeast with Naga cultural immersion.",
        "mid", "moderate", "balanced", "6-8 travelers", 8, 15000,
        ["Dzukou Valley in full bloom with Dzukou lily", "Naga warrior village homestay", "Traditional Naga cuisine and rice beer", "Kohima War Cemetery WW2 history"],
        ["Village homestay + tent", "All meals Naga cuisine", "Local Naga guide", "Dzukou camping permit", "Dimapur coordination"],
        ["Arrive Kohima & War Cemetery Walk", "Drive to Viswema & Trek Start", "Dzukou Valley Camp", "Valley Exploration Day", "Return Trek & Naga Village Night"],
        [{"question": "Nagaland safe for tourists?", "answer": "Very safe and welcoming. Naga people famous for hospitality."},
         {"question": "Special permit needed?", "answer": "Indian nationals no permit. Foreigners need Inner Line Permit, we assist."}],
        5,
    ),
    (
        "demo_kavitha", "Khajuraho Temples & Orchha Fort", "culture-heritage", "Madhya Pradesh",
        "3-day heritage circuit through two of India's most underrated UNESCO sites.",
        "budget", "easy", "balanced", "6-10 travelers", 10, 7000,
        ["Khajuraho Western Group temples at sunrise UNESCO", "Orchha Fort cenotaphs by Betwa River", "Chaturbhuj Temple unique form", "Khajuraho classical dance performance"],
        ["Guesthouse 2 nights", "Daily breakfast", "ASI guide", "Sound-and-light show entry", "Jhansi transfers"],
        ["Arrive Khajuraho & Western Temples Walk", "Eastern Group Temples & Drive to Orchha", "Orchha Fort & Depart"],
        [{"question": "Are temples explicit?", "answer": "Erotic carvings are 10% of total art. Temples celebrate all aspects of life."},
         {"question": "Worth adding Orchha?", "answer": "Absolutely, 3 hours away and often more impressive with fewer tourists."}],
        3,
    ),
    (
        "demo_yusuf", "Lonar Crater Lake & Ajanta Caves", "adventure-sports", "Maharashtra",
        "3-day geological wonder and ancient art combo — 52,000-year-old meteor crater and 2nd-century Buddhist caves.",
        "budget", "moderate", "balanced", "6-10 travelers", 10, 8500,
        ["Lonar Crater Lake world's oldest saline meteor impact lake", "Ajanta Caves 2nd century BCE Buddhist paintings", "Daitya Sudan Temple inside crater", "Ajanta Gorge amphitheater sunrise"],
        ["Guesthouse 2 nights", "Breakfast + 1 dinner", "ASI guide at Ajanta", "Lonar crater trail", "Aurangabad transport"],
        ["Arrive Aurangabad & Lonar Drive", "Lonar Crater Walk & Temple", "Ajanta Caves & Return"],
        [{"question": "Age of Ajanta paintings?", "answer": "Oldest 2nd century BCE. Mahayana period 5th century CE most vivid."},
         {"question": "Lonar crater size?", "answer": "1.8km diameter, 150m deep, strongly saline alkaline lake."}],
        3,
    ),
    (
        "demo_leila", "Cappadocia Hot Air Balloon & Cave Stays", "adventure-sports", "Cappadocia, Turkey",
        "4 days floating over fairy chimneys, sleeping in cave hotels, and exploring underground cities.",
        "premium", "easy", "relaxed", "4-6 travelers", 6, 40000,
        ["Sunrise hot air balloon over Rose Valley", "Cave hotel in Goreme carved from volcanic tufa", "Derinkuyu underground city 8 levels deep", "ATV tour through Pigeon Valley and canyon"],
        ["Cave hotel 3 nights", "Daily breakfast + 1 dinner", "Hot air balloon 1.5 hours", "ATV rental and guide", "Derinkuyu entry"],
        ["Arrive Goreme & Valley Walk", "Balloon Sunrise & Underground City", "ATV Canyon Tour & Local Winery", "Uchisar Castle & Depart"],
        [{"question": "Balloon safe?", "answer": "Regulated by Turkish civil aviation. 15+ years incident-free operator."},
         {"question": "Flight cancelled for weather?", "answer": "Backup morning reserved. Partial refund if both attempts prevented."}],
        4,
    ),
    (
        "demo_elena", "Lisbon & Porto Portugal Food Trail", "food-culture", "Lisbon & Porto, Portugal",
        "5 days in Portugal's two most photogenic cities — pasteis de nata, francesinha, and Douro wine.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 26000,
        ["Belem pasteis de nata at original factory", "Porto Ribeira waterfront and francesinha", "Douro Valley wine estate and port tasting", "Sintra royal palaces day trip"],
        ["Boutique guesthouse 4 nights", "Daily breakfast + 2 dinners", "Douro Valley wine tour", "Sintra day trip", "Lisbon-Porto travel"],
        ["Arrive Lisbon & Alfama Walk", "Belem Tower & Pasteis & Sintra Day", "Train to Porto & Ribeira Walk", "Douro Valley Wine Tour", "Porto Food Crawl & Depart"],
        [{"question": "Portugal expensive?", "answer": "One of Europe's most affordable. Excellent value."},
         {"question": "Need Portuguese?", "answer": "No, English widely spoken in both cities."}],
        5,
    ),
    (
        "demo_kiran", "Scottish Highlands & Isle of Skye", "road-trip", "Scottish Highlands",
        "6-day road trip through dramatic Highland landscapes, lochs, and the mystical Isle of Skye.",
        "premium", "moderate", "balanced", "4-6 travelers", 6, 42000,
        ["Old Man of Storr rock formation at sunrise", "Eilean Donan Castle loch reflection", "Fairy Pools crystal blue hike", "Glencoe valley most dramatic Highland scenery"],
        ["B&B and inn 5 nights", "Daily breakfast + 2 dinners", "Private vehicle + driver", "All entry fees", "Whisky distillery tour"],
        ["Arrive Inverness & Loch Ness", "Glencoe & Fort William", "Skye Eilean Donan & Portree", "Old Man of Storr & Fairy Pools", "Return via Cairngorms", "Depart Edinburgh"],
        [{"question": "Midges in Highlands?", "answer": "Yes in summer near water. Midge nets and repellent provided."},
         {"question": "Skye accessible by car?", "answer": "Yes, Skye Bridge connects mainland. No ferry needed."}],
        6,
    ),
    (
        "demo_amara", "Zanzibar Spice Island & Dhow Cruise", "coastal", "Zanzibar, Tanzania",
        "5 days on the spice island — Stone Town UNESCO site, pristine beaches, and dhow sailing.",
        "mid", "easy", "relaxed", "6-8 travelers", 8, 30000,
        ["Stone Town spice walk with local guide", "Nungwi Beach whitest sand East Africa", "Traditional dhow sunset sailing", "Prison Island giant tortoise sanctuary"],
        ["Boutique hotel 4 nights", "Daily breakfast + 2 dinners", "All boat transfers", "Spice farm tour", "Prison Island entry"],
        ["Arrive Zanzibar & Stone Town Walk", "Spice Farm Tour & Dhow Sunset", "Nungwi Beach Day", "Prison Island & Dolphin Snorkel", "Depart"],
        [{"question": "Best beach on Zanzibar?", "answer": "Nungwi for calm lagoon water. Paje for kitesurfing."},
         {"question": "Safe?", "answer": "Very safe. Mixed Arab, African, Indian cultural history."}],
        5,
    ),
    (
        "demo_sanika", "Kolkata Sweets Street Food & Arts", "food-culture", "Kolkata, West Bengal",
        "3 days in the city of joy — mishti doi, kathi rolls, adda culture, and culinary heritage.",
        "budget", "easy", "balanced", "6-10 travelers", 12, 7000,
        ["Mishti doi and sandesh at Balaram Mullick's", "Kathi roll at original Nizam's restaurant", "College Street para adda culture walk", "New Market and Park Street food history"],
        ["Hotel 2 nights", "All tastings 15+ items", "Cultural food guide", "Ferry on Hooghly River", "Train to New Market"],
        ["Arrive Kolkata & Park Street Evening Walk", "Balaram's & College Street Food Walk", "New Market Kathi Roll Trail & Depart"],
        [{"question": "What is adda culture?", "answer": "Kolkata tradition of lively intellectual discussion over tea and snacks."},
         {"question": "Kolkata street food safe?", "answer": "Reputable establishments selected. High hygiene standards."}],
        3,
    ),
    (
        "demo_rajan", "Coorg to Nagarhole Wildlife", "road-trip", "South Karnataka",
        "4-day road and wildlife combo through Karnataka's coffee hills and tiger reserve.",
        "mid", "easy", "balanced", "4-6 travelers", 6, 14000,
        ["Nagarhole National Park South India's best tiger reserve", "Coorg Abbey Falls trekking trail", "Coffee estate sunset with filter coffee", "Kabini River boat safari"],
        ["Estate homestay + eco-resort 3 nights", "All meals", "Safari fees", "Kabini boat safari", "AC vehicle throughout"],
        ["Bengaluru Departure & Coorg Arrival", "Coffee Estate Day & Abbey Falls", "Drive to Kabini & Boat Safari", "Nagarhole Morning Safari & Return"],
        [{"question": "Chances of seeing tiger?", "answer": "Nagarhole excellent tiger population. Morning Zone A safaris best probability."},
         {"question": "Can I add Mysore visit?", "answer": "Yes, Mysore 90 minutes from Coorg, extend on request."}],
        4,
    ),
    (
        "demo_priya", "Pondicherry Yoga & French Quarter", "wellness", "Pondicherry, Tamil Nadu",
        "3-day wellness escape in the French colonial town — ashram yoga, beach meditation, and cafe culture.",
        "budget", "easy", "relaxed", "6-8 travelers", 8, 8000,
        ["Sunrise yoga at Sri Aurobindo Ashram", "White Town French Quarter cycle tour", "Serenity Beach early morning meditation", "French Indic cafe culture on Rue Saint-Louis"],
        ["Boutique guesthouse 2 nights", "Daily breakfast", "Ashram yoga session", "Bicycle rental", "Beach meditation guide"],
        ["Arrive Pondy & French Quarter Walk", "Ashram Yoga Morning & Beach Afternoon", "Auroville & Depart"],
        [{"question": "Ashram open to outsiders?", "answer": "Yes, yoga and meditation programs with advance registration."},
         {"question": "Safe for solo women?", "answer": "Very much yes. One of India's safest cities for solo travel."}],
        3,
    ),
    (
        "demo_yusuf", "Sandakphu Trek: Roof of West Bengal", "trekking", "Sandakphu, Darjeeling",
        "6-day trek to the highest point in West Bengal — views of 4 of the world's 5 highest peaks.",
        "mid", "moderate", "balanced", "6-10 travelers", 10, 14500,
        ["Sandakphu summit: see Everest Kanchenjunga Lhotse Makalu simultaneously", "Phalut viewpoint panoramic sunrise", "Sleeping Buddha silhouette from Tumling", "Darjeeling toy train section"],
        ["Trekkers huts", "All meals", "Guide + porter", "Trekking permit", "NJP or Bagdogra pickup"],
        ["Arrive Darjeeling & Manebhanjang", "Chitrey to Tumling", "Tumling to Kalipokhri", "Summit Sandakphu", "Phalut Viewpoint", "Return to Darjeeling & Depart"],
        [{"question": "Can I see Everest?", "answer": "Yes! On clear days see Everest, Kanchenjunga, Lhotse, Makalu simultaneously."},
         {"question": "Best season?", "answer": "Oct-Nov for clear mountain views. Mar-Apr for rhododendron bloom."}],
        6,
    ),
    (
        "demo_kavitha", "Belur & Halebidu Hoysala Temples", "culture-heritage", "Hassan, Karnataka",
        "2-day deep dive into the masterpieces of Hoysala sculpture — 12th-century stone carvings.",
        "budget", "easy", "relaxed", "6-10 travelers", 10, 5500,
        ["Belur Channakeshava Temple 117 years of sculptural work", "Halebidu Hoysaleshwara lathe-turned pillars", "500+ unique sculptures on single temple exterior", "Shravanabelagola Jain pilgrimage optional"],
        ["Heritage guesthouse 1 night", "Breakfast and 1 lunch", "ASI-licensed guide", "Temple entry fees", "Bengaluru transfer"],
        ["Arrive Hassan & Belur Temple", "Halebidu Temple & Return Bengaluru"],
        [{"question": "Why less famous than Khajuraho?", "answer": "Both masterpieces. Belur focuses on celestial damsels and epics. Stone harder, carvings sharper."},
         {"question": "Add Shravanabelagola?", "answer": "58-foot Jain statue is 30 min from Halebidu. Optional half-day extension."}],
        2,
    ),
    (
        "demo_nisha", "Bikaner Camel Festival & Heritage", "desert", "Bikaner, Rajasthan",
        "3-day Bikaner camel festival — decorated camel parades, folk performances, and Junagarh Fort.",
        "budget", "easy", "relaxed", "6-10 travelers", 10, 7000,
        ["Bikaner Camel Festival parade ground", "Junagarh Fort galleries and armory", "Karni Mata Rat Temple unique spiritual experience", "Bikaner bhujia and sweets market walk"],
        ["Heritage hotel 2 nights", "Breakfast + 1 dinner", "Festival entry pass", "Fort guided tour", "Local food guide"],
        ["Arrive Bikaner & Camel Festival Parade", "Junagarh Fort & Karni Mata Temple", "Local Market Walk & Depart"],
        [{"question": "When is Bikaner Camel Festival?", "answer": "January annually. Government-organized event with international visitors."},
         {"question": "Karni Mata temple really full of rats?", "answer": "Yes, thousands of sacred rats roam freely. Shoes off required."}],
        3,
    ),
    (
        "demo_tao", "Penang Food & Heritage Walk", "food-culture", "Penang, Malaysia",
        "3 days in Asia's food capital — Char Kway Teow, Laksa, Nasi Lemak, and George Town's street art.",
        "budget", "easy", "balanced", "6-10 travelers", 10, 10000,
        ["Char Kway Teow at Lorong Selamat world's best flat noodles", "Penang Laksa at Air Itam stall", "George Town street art mural bicycle trail", "Nasi Kandar Line Clear 3am stall"],
        ["Guesthouse 2 nights", "All food tastings", "Heritage walk guide", "Trishaw ride George Town", "Butterworth ferry"],
        ["Arrive Penang & George Town Night Food Walk", "Hawker Centre Deep Dive & Street Art Trail", "Final Tastings & Heritage Sites & Depart"],
        [{"question": "Suitable for vegetarians?", "answer": "Excellent Indian vegetarian options. Buddhist vegetarian stalls everywhere."},
         {"question": "Compare to India?", "answer": "Penang hawker food rivals any street food culture globally. Indian influence makes it familiar."}],
        3,
    ),
    (
        "demo_amara", "Ethiopian Highlands & Lalibela Churches", "culture-heritage", "Lalibela & Simien Mountains",
        "7 days in one of Africa's oldest civilizations — rock-hewn churches, mountain trekking, and ancient coffee ritual.",
        "mid", "moderate", "balanced", "4-6 travelers", 6, 30000,
        ["Lalibela Church of St George carved 40m into earth", "Ethiopian coffee ceremony with local family", "Simien Mountains gelada baboon encounter", "Blue Nile Falls Africa's widest waterfall"],
        ["Hotel and guesthouse 6 nights", "All meals injera teff bread", "Local guide and cultural interpreter", "Simien Mountains trek permit", "Domestic flights from Addis"],
        ["Arrive Addis Ababa & National Museum", "Fly to Lalibela & Rock Church Tour", "Lalibela Deep Sites & Ceremonies", "Fly to Gondar & Castles Walk", "Simien Mountains Trek Day 1", "Gelada Baboons & Ras Dashan View", "Return Addis & Depart"],
        [{"question": "Vaccinations needed?", "answer": "Yellow fever required. Typhoid and Hepatitis A recommended."},
         {"question": "Food for non-adventurous eaters?", "answer": "Ethiopian injera and lentil wot delicious. Western options at hotels."}],
        7,
    ),
    (
        "demo_kiran", "Prague & Cesky Krumlov Weekend", "city", "Czech Republic",
        "4 days in Central Europe's most photogenic city and a fairy-tale castle town.",
        "mid", "easy", "balanced", "6-8 travelers", 8, 26000,
        ["Prague Castle complex at dawn", "Charles Bridge at golden hour", "Cesky Krumlov UNESCO castle & river bend", "Czech pub crawl pilsner at Lokal"],
        ["Boutique hotel 3 nights", "Daily breakfast + 1 dinner", "Prague Castle skip-the-line", "Cesky Krumlov day trip", "Metro + tram pass"],
        ["Arrive Prague & Old Town Walk", "Prague Castle & Mala Strana", "Cesky Krumlov Day Trip", "Vinohrady Neighborhood & Depart"],
        [{"question": "Prague expensive?", "answer": "One of Europe's best value cities. Beer cheaper than water."},
         {"question": "Czech Republic Schengen?", "answer": "Yes, Indian passport requires Schengen visa. Invitation letters provided."}],
        4,
    ),
    (
        "demo_elena", "Iceland Northern Lights & Waterfalls", "adventure-sports", "Iceland",
        "6 days chasing the Aurora Borealis and Iceland's extraordinary geological landscapes.",
        "premium", "moderate", "balanced", "4-6 travelers", 6, 52000,
        ["Northern Lights Aurora Borealis hunt Oct-Mar", "Seljalandsfoss waterfall walk behind the falls", "Vatnajokull glacier hike with crampons", "Blue Lagoon geothermal spa"],
        ["Boutique hotel + guesthouse 5 nights", "Daily breakfast + 2 dinners", "Northern lights evening excursion", "Glacier hike with crampons + guide", "Blue Lagoon entry"],
        ["Arrive Reykjavik & City Walk", "Golden Circle Geysir Gullfoss Thingvellir", "South Coast Black Beach & Seljalandsfoss", "Jokulsarlon Glacier Lagoon & Ice Cave", "Glacier Hike & Blue Lagoon", "Depart"],
        [{"question": "Northern Lights guaranteed?", "answer": "No, depends on solar activity. Oct-Feb best probability. 2-3 attempts per trip."},
         {"question": "Iceland in winter?", "answer": "Expect -5 to -10C. Cold weather packing list provided."}],
        6,
    ),
    (
        "demo_arjun", "Hampta Pass Camping Expedition", "camping", "Manali to Spiti",
        "6-day dramatic crossing of Hampta Pass from green Kullu Valley to barren Spiti Valley.",
        "mid", "challenging", "fast", "6-8 travelers", 8, 14500,
        ["Hampta Pass at 4,270m crossing of two worlds", "Shea Goru camp with glacier views", "River crossing at Jwara camp", "Chandratal moonlit lake optional extension"],
        ["Full camping setup", "All meals during trek", "Certified mountain guide", "Porterage included", "Manali transfer"],
        ["Arrive Manali & Gear Check", "Jobra to Chika", "Chika to Balu Ka Ghera", "Summit Hampta Pass to Shea Goru", "Shea Goru to Chatru", "Optional Chandratal & Return"],
        [{"question": "What makes Hampta Pass unique?", "answer": "Cross from lush green Kullu 1,900m to barren Spiti moonscape 3,600m in one day."},
         {"question": "River crossing dangerous?", "answer": "Knee-deep in summer melt. Ropes used, cross in morning when water lower."}],
        6,
    ),
    (
        "demo_priya", "Rishikesh Yoga & Meditation Retreat", "wellness", "Rishikesh, Uttarakhand",
        "5 days in the yoga capital of the world — morning asana, Ayurveda, and Ganga meditation.",
        "budget", "easy", "relaxed", "6-10 travelers", 10, 9500,
        ["Sunrise yoga at Parmarth Niketan on the Ganga", "Evening Ganga Aarti at Triveni Ghat", "Ayurvedic consultation and treatment", "Silent meditation walk to Neelkanth Temple"],
        ["Ashram 4 nights", "Sattvic meals", "Daily yoga 2 sessions per day", "Ayurvedic consultation", "Rafting option extra"],
        ["Arrive Rishikesh & Aarti Evening", "Yoga Intensive Day 1 & Ayurvedic Consultation", "Yoga Day 2 & Neelkanth Temple Walk", "Silent Day & River Meditation", "Final Ceremony & Depart"],
        [{"question": "Must be vegetarian?", "answer": "Ashram serves sattvic food. Non-veg available in town."},
         {"question": "Yoga style?", "answer": "Hatha and Ashtanga, instructor adapts to group level."}],
        5,
    ),
    (
        "demo_rajan", "North East India Meghalaya & Assam", "road-trip", "Meghalaya & Assam",
        "7-day road journey through India's northeast — living root bridges, tea gardens, and rhino reserve.",
        "mid", "moderate", "balanced", "4-6 travelers", 6, 20000,
        ["Cherrapunji double-decker living root bridge", "Kaziranga National Park one-horned rhino safari", "Mawlynnong Asia's cleanest village", "Elephant safari in Kaziranga"],
        ["Eco-lodge and guesthouse 6 nights", "All meals", "Kaziranga jeep safari", "Root bridge trek guide", "Guwahati airport transfer"],
        ["Arrive Guwahati & Drive to Kaziranga", "Kaziranga Morning Safari", "Drive to Shillong & Elephant Falls", "Cherrapunji Root Bridges Trek Day 1", "Root Bridge Trek Day 2 & Mawlynnong", "Return to Guwahati via Umiam Lake", "Depart"],
        [{"question": "Root bridge trek difficult?", "answer": "2,400+ steps each way. Challenging but achievable in 4-5 hours."},
         {"question": "Animals at Kaziranga?", "answer": "One-horned rhino 2,000+, elephant, wild buffalo, tigers. Rhino sighting near-guaranteed."}],
        7,
    ),
    (
        "demo_kavitha", "Tamil Nadu Temple Circuit", "culture-heritage", "Tamil Nadu",
        "5-day Dravidian temple circuit — Madurai Meenakshi, Thanjavur Brihadeeswarar, and Chidambaram.",
        "budget", "easy", "relaxed", "6-10 travelers", 12, 9000,
        ["Meenakshi Amman Temple 33,000 sculptures 1,500 pillars", "Brihadeeswarar Temple Thanjavur UNESCO", "Chidambaram Nataraja dancing Shiva", "Kumbakonam 20+ ancient tanks and temples"],
        ["Budget hotel 4 nights", "Breakfast + 2 group meals", "Licensed temple guide mandatory", "State bus passes", "Temple entry offerings"],
        ["Arrive Madurai & Meenakshi Temple", "Float Festival Pond & Nayakar Palace", "Drive to Thanjavur & Brihadeeswarar", "Kumbakonam Temples & Gangaikondacholapuram", "Chidambaram Nataraja & Depart"],
        [{"question": "Non-Hindus allowed?", "answer": "Outer precincts open to all. Inner sanctums restricted to Hindus."},
         {"question": "How tiring?", "answer": "2-3 hours walking per temple on stone floors. Comfortable footwear essential."}],
        5,
    ),
    (
        "demo_nisha", "Hemis Festival & Ladakh Buddhism", "culture-heritage", "Leh-Ladakh",
        "5 days in Ladakh during Hemis Festival — the region's most spectacular Buddhist masked dance festival.",
        "mid", "easy", "balanced", "4-6 travelers", 6, 19000,
        ["Hemis Festival Cham dance performances", "Thiksey Monastery sunrise panorama", "Diskit Monastery and giant Maitreya Buddha", "Pangong Tso crystalline blue lake 4,350m"],
        ["Hotel 4 nights", "Breakfast + 2 dinners", "Festival entry and ground access", "All monastery visits", "Leh airport pickup"],
        ["Arrive Leh & Acclimatization Day", "Hemis Festival Day 1 & Thiksey Monastery", "Hemis Festival Day 2 & Shey Palace", "Drive to Nubra Valley", "Pangong & Return"],
        [{"question": "When is Hemis Festival?", "answer": "Jun-Jul Tibetan month Tse-chu. Timed to 2-day main festival."},
         {"question": "Altitude concern at Leh?", "answer": "Leh at 3,524m. 2 acclimatization days built in. No exercise or alcohol on arrival day."}],
        5,
    ),
    (
        "demo_amara", "Cape Town & Garden Route Road Trip", "road-trip", "South Africa",
        "8-day South Africa road trip — Table Mountain, wine lands, and Garden Route coastal drive.",
        "premium", "easy", "balanced", "4-6 travelers", 6, 48000,
        ["Table Mountain cable car at sunrise", "Cape of Good Hope penguin colony", "Stellenbosch wine estate tasting", "Tsitsikamma National Park suspension bridge"],
        ["Boutique hotel and guesthouse 7 nights", "Daily breakfast + 2 dinners", "Private vehicle + driver", "All national park entries", "Table Mountain and wine estate tours"],
        ["Arrive Cape Town & V&A Waterfront", "Table Mountain & Cape of Good Hope", "Stellenbosch & Franschhoek Wine Day", "Drive to Hermanus Whale Watching", "Mossel Bay & Wilderness Beach", "Tsitsikamma Park & Suspension Bridge", "Drive to George for Depart", "Fly Back to Cape Town Hub"],
        [{"question": "South Africa safe for tourists?", "answer": "Stick to tourist areas. Cape Town and Garden Route well-managed."},
         {"question": "Best time for whale watching?", "answer": "Jun-Nov Southern Right Whales at Hermanus."}],
        8,
    ),
]

# ── Blog seed data ──────────────────────────────────────────────────────────────
# (host, slug, title, excerpt, body, location, tags, reads)

BLOG_SEEDS = [
    ("demo_arjun", "how-to-plan-first-himalayan-trek",
     "How to Plan Your First Himalayan Trek: A Complete Guide",
     "Planning a Himalayan trek for the first time? Here's everything you need to know — from fitness prep to permit paperwork.",
     "The Himalayas are calling you, but where do you start? After guiding 200+ treks I've compiled everything first-time trekkers need.\n\n**Choosing the Right Trek**\nStart with Kedarkantha (3,810m) or Kasol-Kheerganga (2,950m). Both are accessible with spectacular views without technical climbing.\n\n**Fitness Preparation**\nBegin 8 weeks before: 45-minute jogs 3x/week, stair climbing daily, and yoga for flexibility.\n\n**Permits**\nMost treks need a trekking permit (INR 200-400) from local DFO offices. Foreign nationals need Inner Line Permits for restricted areas like Roopkund and Chopta.\n\n**Packing Essentials**\nWarm layers (merino wool), waterproof jacket, trekking poles, headlamp, first aid kit, high-energy snacks, sleeping bag rated to -10C for camps above 3,500m.",
     "Uttarakhand, India", ["trekking", "himalaya", "beginner", "guide"], 14200),
    ("demo_priya", "goa-beyond-the-tourist-beaches",
     "Goa Beyond the Beaches: Spice Farms, Hidden Temples & Village Life",
     "Most travelers never leave North Goa's party belt. But the real Goa is in the villages, spice plantations, and centuries-old temples.",
     "After 7 years of hosting coastal retreats in Goa I'm convinced the tourists who love it most went looking beyond Baga and Calangute.\n\n**Spice Plantations**\nThe Ponda district hinterland has 50+ spice farms. Sahakari Spice Farm offers guided walks where you identify cardamom, vanilla, nutmeg, and pepper in their natural state — followed by traditional Goan lunch.\n\n**Temple Circuit**\nGoa has architecturally unique temples. Mangueshi Temple near Ponda blends Hindu and Portuguese Baroque. Tambdi Surla Mahadeva Temple (12th century) deep in the Western Ghats is a forgotten Kadamba masterpiece.\n\n**Village Walks**\nSaligao, Assagao, and Aldona in North Goa have beautiful Portuguese-style houses, quiet lanes, and extraordinary architecture. Hire a bicycle from Mapusa and spend a morning — you'll have them almost to yourself.",
     "Goa, India", ["goa", "india", "offbeat", "culture", "temples"], 11800),
    ("demo_kavitha", "decoding-south-indian-temple-architecture",
     "Decoding South Indian Temple Architecture: A Beginner's Field Guide",
     "Gopurams, mandapams, vimanas — South Indian temples have a language of their own. Here's how to read it.",
     "Standing at the base of the 49-metre Meenakshi Amman gopuram in Madurai, most visitors feel overwhelmed by the sheer density of sculpture.\n\n**The Gopuram**\nThe entrance gateway (gopuram) represents Mount Meru — the cosmic mountain at the center of the Hindu universe. The number of tiers indicates importance. Meenakshi has 14 gopurams; the tallest are 46m and 49m.\n\n**The Vimana**\nThe tower above the main shrine is the vimana. At Brihadeeswarar Thanjavur, the 66-metre vimana was built in 1010 CE and still stands without any lateral support.\n\n**Reading the Sculptures**\nLower tiers show Puranic scenes (mythological stories). Upper tiers become increasingly abstract, representing ascent toward the divine. Vishnu always holds a conch and discus; Shiva holds a trident and has a third eye.",
     "Tamil Nadu, India", ["culture", "temples", "heritage", "south-india", "architecture"], 8900),
    ("demo_sanika", "india-ultimate-street-food-guide",
     "India's Ultimate Street Food Guide: City by City",
     "From Mumbai's Vada Pav to Kolkata's Kathi Roll — India's street food is a 5,000-year-old conversation between spices, cultures, and hungry people.",
     "I've eaten on 340+ streets across 22 Indian cities. Here are the non-negotiable stops.\n\n**Mumbai**\nStart at Dadar's Vijay Sandwich for the butter-dripping Bombay Sandwich. Move to Swati Snacks for the best pani puri. End at Mohammed Ali Road for seekh kebab and shahi tukda at midnight.\n\n**Delhi**\nParanthe Wali Gali in Chandni Chowk for stuffed paranthas. Natraj Dahi Bhalle Wala for bhalle served since 1940.\n\n**Kolkata**\nNizam's restaurant for the original Kathi Roll. Balaram Mullick and Radharaman Mullick for sandesh and mishti doi.\n\n**Chennai**\nMurugan Idli Shop chains for consistently excellent idli-vada-sambhar. Ratna Cafe for weekend special mutton kheema.",
     "Pan-India", ["food", "street-food", "india", "travel", "guide"], 16500),
    ("demo_rajan", "ladakh-motorcycle-trip-complete-guide",
     "Ladakh Motorcycle Trip: Everything Nobody Tells You",
     "The Leh-Manali highway is one of the world's great road trips. Here's what the Instagram photos leave out.",
     "3 motorcycle expeditions to Ladakh over 8 years. Here's what I wish I'd known the first time.\n\n**Acclimatization is Not Optional**\nI rode straight from Chandigarh to Leh in 2 days on my first trip. Spent day 3 with splitting headache and nausea. Spend 2 nights at Sarchu (4,300m) and 1 full acclimatization day in Leh before riding further.\n\n**The Bike Question**\nRoyal Enfield Himalayan is best for first-timers. 411cc, long-travel suspension, parts available everywhere. Avoid standard Bullets above 4,500m — they struggle.\n\n**Water Crossing Tips**\nEnter river crossings at 45-degree angle upstream, never straight across. Engine must be warm. Never stop in middle.\n\n**Weather Windows**\nJuly-September for road conditions. September is ideal — post-monsoon clarity for Pangong and fewer riders on Khardung La.",
     "Leh-Ladakh, India", ["ladakh", "motorcycle", "roadtrip", "adventure", "himalaya"], 13700),
    ("demo_amara", "east-africa-safari-preparation-guide",
     "East Africa Safari: The Preparation Guide You Actually Need",
     "Masai Mara, Serengeti, Amboseli — first-time safari travelers ask the same 40 questions. Here are the answers.",
     "I've guided over 180 safaris across Kenya, Tanzania, and Uganda. The questions never change — only the faces.\n\n**When to Go**\nGreat Wildebeest Migration: July-October in Masai Mara for river crossings. January-March in Serengeti for calving season.\n\n**Budget Reality**\nBudget safaris ($80-150/night) use shared minibuses and often miss off-road driving permissions. Mid-range ($200-350) uses private jeeps with better guide ratios.\n\n**Camera Equipment**\n100-400mm telephoto zoom for wildlife. Wide lens for landscapes. NO flash — distresses animals and is prohibited in most reserves.\n\n**Malaria Reality**\nAtovaquone-proguanil (Malarone) is most effective prophylaxis. Start 2 days before arrival, continue 7 days after departure.",
     "East Africa", ["safari", "kenya", "tanzania", "wildlife", "guide", "africa"], 12400),
    ("demo_leila", "uae-luxury-travel-insider-tips",
     "UAE Luxury Travel: What Only Insiders Know",
     "Dubai gets all the attention, but the real luxury travel secret is knowing where the locals go.",
     "After 6 years of designing premium travel experiences in the UAE, I've learned the most extraordinary moments aren't at the Burj Khalifa.\n\n**Where Locals Eat in Dubai**\nAl Ustad Special Kabab in Deira (established 1978) serves the best Iranian grilled fish in the city. Ravi Restaurant in Satwa for Pakistani karahi at 3am.\n\n**Desert Experiences Beyond Tourist Camps**\nThe Liwa Oasis road trip (200km from Abu Dhabi) crosses the largest dunes in the Arabian Peninsula — Moreeb Dune rises 300m. In winter, spectacularly empty.\n\n**Sharjah Arts Secret**\nSharjah is 20 minutes from Dubai with one of the Middle East's finest Islamic calligraphy collections at the Sharjah Art Museum. Free entry. Almost always empty.",
     "UAE & Dubai", ["uae", "dubai", "luxury", "premium", "middleeast"], 9200),
    ("demo_tao", "singapore-hawker-centres-guide",
     "Singapore's Hawker Centres: The Definitive Eating Guide",
     "Singapore has 114 hawker centres. Here are the 6 you actually need, with the specific stalls that justify the detour.",
     "Born in Singapore, lived here 32 years, eaten at 90+ hawker centres. Here is my completely biased, maximally useful guide.\n\n**Maxwell Food Centre (Chinatown)**\nTian Tian Hainanese Chicken Rice (stall 01-10) — consistently ranked one of world's best chicken rice. Queue at 11:30am before it sells out.\n\n**Old Airport Road Food Centre (Geylang)**\nBeef Hor Fun stall (Zhen Zhen, arrive 7am). Also best rojak in Singapore at stall 01-131.\n\n**Tiong Bahru Market**\nRi Ri Hong Mee Pok for handmade minced pork noodles. Xin Yue Wonton Noodle (queue by 8am on weekends or it's gone).",
     "Singapore", ["singapore", "food", "hawker", "asia", "guide"], 11200),
    ("demo_elena", "barcelona-local-neighborhood-guide",
     "Living Barcelona: A Neighborhood Guide Beyond Las Ramblas",
     "Tourists crowd Las Ramblas. Locals live in Gracia, Poble Sec, and Sarria. Here's how to see Barcelona like a resident.",
     "After 5 years of hosting cultural tours in Barcelona, I can tell you exactly where tourists go wrong: they stay on Las Ramblas.\n\n**Gracia District**\nThe most residential neighborhood in Barcelona. The squares (Placa del Sol, Placa de la Vila) fill with locals every evening from 7pm. Buy wine from a bodega, sit on the square, and watch Barcelona life unfold.\n\n**Poble Sec & Montjuic**\nAvenida del Paralel is having its revival. Refugi 307 Civil War bunker is one of the city's best-kept secrets — a 1,200m underground shelter from 1936.\n\n**Sarria Village**\nAt the foot of Collserola Natural Park, Sarria is a village swallowed by the city but never losing its character. The Passeig de la Reina Elisenda street market on Saturdays is a local institution.",
     "Barcelona, Spain", ["barcelona", "spain", "travel", "culture", "local-tips"], 9800),
    ("demo_kiran", "london-free-things-to-do",
     "London Free & Cheap: 30 Things That Cost Nothing",
     "London's most common travel complaint is the price. Here are 30 things that are free or cost less than a coffee.",
     "London is expensive, but its best museums are free, its parks extraordinary, and its markets world-class.\n\n**Free World-Class Museums**\nThe British Museum (Rosetta Stone and Elgin Marbles), Natural History Museum (blue whale skeleton), V&A Museum (world's greatest decorative arts collection), National Gallery (van Gogh, Turner, da Vinci), Tate Modern (contemporary art in converted power station).\n\n**Free Parks**\nHyde Park, Regent's Park, Hampstead Heath (swim in the ponds in summer). Kew Gardens is not free (18 pounds) but the park at sunset in autumn is worth every penny.\n\n**Free Architecture**\nSt Paul's Cathedral exterior, Borough Market (free to browse), Columbia Road Flower Market (Sunday mornings), Leadenhall Market (Victorian covered market).",
     "London, UK", ["london", "uk", "budget-travel", "europe", "guide"], 13900),
    ("demo_nisha", "rajasthan-palace-hotels-worth-booking",
     "Rajasthan's Palace Hotels: Which Ones Are Actually Worth It",
     "India has 300+ palace and heritage hotels. Here's how to separate the genuine article from the painted concrete variety.",
     "After 12 years of hosting heritage tours in Rajasthan, I've stayed in 40+ palace properties. The quality range is extraordinary.\n\n**Genuine Heritage That Delivers**\nWelcomeHeritage Mandir Palace Jaisalmer — 400-year-old royal residence with functioning havelis. Rawla Narlai — 17th-century hunting lodge between Jodhpur and Udaipur, 40 rooms, extraordinary hospitality. Best sunset in Rajasthan from the rooftop.\n\n**Non-Negotiables**\nAmanbagh near Alwar — not historically a palace but built with palace sensibility. SUJAN Sher Bagh in Ranthambore — luxury tented camp, most atmospheric property in Rajasthan.\n\n**Consider Carefully**\nThe Taj Lake Palace in Udaipur is beautiful on the outside but operationally inconsistent. The boat transfer delays are frustrating.",
     "Rajasthan, India", ["rajasthan", "heritage", "palaces", "hotels", "india"], 10600),
    ("demo_arjun", "altitude-sickness-prevention-guide",
     "Altitude Sickness: Prevention, Recognition, and the Descent Rule",
     "AMS kills every year. Here's how to spot it, prevent it, and what you must do when it strikes.",
     "In 8 years of guiding Himalayan treks, I've had to make the emergency descent call 7 times. Here's the knowledge that might save your life.\n\n**What is AMS?**\nAcute Mountain Sickness occurs when the body can't acclimatize fast enough to reduced oxygen pressure at altitude. Affects 25-40% of people above 3,000m regardless of fitness level.\n\n**Symptoms**\nMild: headache, fatigue, loss of appetite. Severe: persistent headache not responding to ibuprofen, vomiting, confusion, ataxia (loss of balance).\n\n**The Golden Rule**\n'Walk high, sleep low.' Never ascend more than 300m per day above 3,000m. Add one rest day for every 1,000m of elevation gain.\n\n**The Descent Rule**\nIf any trekker shows moderate-severe AMS, descend immediately. Never wait until morning. Descent of even 300-500m often brings dramatic improvement.",
     "Himalayan Region", ["trekking", "safety", "altitude", "himalaya", "health"], 17800),
    ("demo_rajan", "india-wildlife-parks-comparison",
     "India's Top Wildlife Parks: An Honest Comparison",
     "Which park gives the best tiger sighting odds? Which has the best birding? Which is most overrated? The answers might surprise you.",
     "After 15 years and 200+ safaris across India's national parks, here's my completely honest comparison.\n\n**Tiger Sightings**\n1. Kanha (Madhya Pradesh) — highest tiger density, largest meadow clearings, best daytime visibility.\n2. Kabini (Karnataka) — best leopard + tiger combo, incredible elephant herds at the reservoir.\n3. Ranthambore (Rajasthan) — most dramatic landscape but highest tourism pressure.\n\n**For Birds**\nBharatpur Keoladeo is the gold standard with 370+ species in a tiny area.\n\n**Most Overrated**\nSariska Tiger Reserve — very low tiger density, heavily touristed. Ranthambore is nearby and dramatically better.",
     "India Wildlife", ["wildlife", "safari", "india", "tiger", "guide"], 12100),
    ("demo_sanika", "onam-sadhya-complete-guide",
     "Onam Sadhya: What Each of the 26 Dishes Is and Why It's There",
     "The Onam Sadhya is one of the world's greatest meals. Here's the full guide to understanding every dish on the banana leaf.",
     "Sadhya means 'banquet' in Malayalam. The Onam feast traditionally has 26+ dishes served in a specific order on a fresh banana leaf. Each dish has a role in Ayurvedic nutrition logic.\n\n**The Sequence**\nBanana chips and pappadums go on the upper left first — crispy items to prepare the palate. Then inji puli (ginger-tamarind relish), pachadi (raita-style side), thoran (dry stir-fried vegetable), aviyal (mixed vegetable coconut curry).\n\n**The Curries**\nSambar and rasam are served as digestive liquids after main courses. Moru (spiced buttermilk) closes the meal. Payasam (sweet pudding — usually two types) signals the formal end.\n\n**The Logic**\nThe Sadhya moves from salty/sour/spicy to sweet, mirroring Ayurvedic meal structure: first stimulate digestion, then nourish, then close with sweet and sour digestives.",
     "Kerala, India", ["kerala", "food", "onam", "sadhya", "culture"], 8400),
    ("demo_amara", "gorilla-trekking-rwanda-guide",
     "Rwanda Gorilla Trekking: What No One Tells You Before You Go",
     "The $1,500 permit is just the beginning. Here's everything first-time gorilla trekkers need to know.",
     "I've facilitated 65+ gorilla trekking experiences in Rwanda and Uganda. The preparation almost always falls short.\n\n**Physical Preparation**\nThe trek can take 2-8 hours depending on where the gorilla family has moved overnight. Train specifically: stair climbs with loaded pack, 5km+ walks on uneven terrain.\n\n**The Permit Reality**\nRwanda's gorilla permit costs $1,500. Uganda charges $700. Rwanda is safer, more organized, with better infrastructure.\n\n**The One Hour Rule**\nOnce you find the gorilla family, you have exactly one hour with them. The trackers enforce this strictly.\n\n**What to Bring**\nLong sleeves and trousers (stinging nettles), gardening gloves, waterproof boots with ankle support, small day pack with raincover, camera with extra battery (no flash).",
     "Rwanda & Uganda", ["gorilla", "rwanda", "africa", "wildlife", "trekking"], 9600),
    ("demo_tao", "vietnam-food-city-by-city",
     "Vietnam Top to Bottom: A Food Guide by City",
     "Vietnamese cuisine changes dramatically every 200km. Here's what to eat in each major city and why.",
     "6 years of food tours across Vietnam. The variety is astonishing.\n\n**Hanoi**\nBun Cha (barbecued pork with rice noodles) is the quintessential Hanoi lunch. Egg coffee at Cafe Giang on Hang Gai street is non-negotiable.\n\n**Hoi An**\nCao Lau — a rice noodle dish that technically exists only in Hoi An (the well water affects the taste). White Rose (white shrimp dumplings) are equally unique.\n\n**Ho Chi Minh City**\nBanh Mi: Saigon fillings are more complex — pate, pickled daikon, chili sauce. Banh Cuon (steamed rice rolls) at Thanh Van on Dinh Tien Hoang for breakfast.\n\n**Da Nang**\nMi Quang (turmeric noodles with peanuts) is the signature dish. Best at small street stalls near Han Market.",
     "Vietnam", ["vietnam", "food", "asia", "travel", "guide"], 11400),
    ("demo_leila", "maldives-budget-vs-luxury-comparison",
     "Maldives on a Budget vs. Luxury: What You Actually Get",
     "The Maldives has a INR 15,000 guesthouse option and a INR 80,000/night water villa option. Here's what changes between them.",
     "I've organized Maldives trips across the full price spectrum.\n\n**Budget (Guesthouse, Local Islands: INR 3,000-8,000/night)**\nYou stay on inhabited islands like Maafushi. The beach is public but excellent. Reef snorkeling from the beach almost as good. The catch: no alcohol on local islands.\n\n**Mid-Range (Resort Island: INR 15,000-30,000/night)**\nPrivate beach resort island, all-inclusive options, water villas start here.\n\n**Luxury (Over-Water Villa: INR 50,000-80,000/night)**\nPrivate villa with glass floor panels over the lagoon, personal butler, direct ladder into the ocean. Quality differential is real but diminishing returns above INR 30,000 are significant.",
     "Maldives", ["maldives", "luxury", "budget", "comparison", "coastal"], 14300),
    ("demo_elena", "spain-beyond-barcelona-madrid",
     "Spain Beyond Barcelona and Madrid: The Places Most Travelers Miss",
     "Spain's most interesting experiences are hiding in Extremadura, Cantabria, and the Basque Country.",
     "I've spent 10 years running tours across Spain. The places that consistently surprise my travelers most have nothing to do with Madrid or Barcelona.\n\n**Extremadura**\nCaceres — a perfectly preserved walled old city with 1,200 years of layered architecture. Merida has the best-preserved Roman theater in the world, still used for performances.\n\n**Cantabria & Asturias**\nThe Green Spain. The Picos de Europa mountain range, the Altamira Cave paintings (17,000 years old), and the fabulous seafood coastline of Asturias.\n\n**Basque Country (San Sebastian)**\nThe world's highest concentration of Michelin stars per capita. Pintxos bars in La Parte Vieja. The surf beaches of Zarautz.",
     "Spain", ["spain", "europe", "travel", "offbeat", "culture"], 8200),
    ("demo_kiran", "european-rail-travel-beginners-guide",
     "European Rail Travel: The Beginner's Complete Guide",
     "Train travel in Europe is fast, comfortable, and often cheaper than flying. Here's how to do it properly.",
     "I've organized rail-only travel across 22 European countries.\n\n**The Eurail Pass Question**\nEurail Passes are only worth it if traveling continuously through 5+ countries. For focused travel (UK + France), point-to-point advance tickets are dramatically cheaper.\n\n**Key Booking Principles**\nBook European trains as early as possible — 3 months ahead for high-speed intercity routes. Prices roughly double in the last 2 weeks.\n\n**Iconic Rail Journeys**\nGlacier Express (Zermatt-St Moritz): 8 hours through 91 tunnels and 291 bridges. Bernina Express: UNESCO World Heritage route through Swiss Alps. The Highland Line (Inverness-Kyle of Lochalsh): Scotland's most scenic rail journey.",
     "Europe", ["europe", "rail", "travel", "guide", "trains"], 10800),
    ("demo_nisha", "travel-photography-golden-hour-india",
     "The Travel Photographer's Guide to Golden Hour in India",
     "India's most photogenic moments happen in the 40 minutes after sunrise and before sunset. Here's how to find them.",
     "In 15 years of travel photography across India, golden hour has given me 80% of my best images.\n\n**Why Golden Hour**\nThe sun at 5-10 degrees above the horizon produces light at 2,000K-3,500K color temperature — warm, directional, and soft. Shadows become dramatic, textures pop.\n\n**India's Best Golden Hour Locations**\n1. Varanasi ghats — the Ganges at dawn reflects the first light. Be on a boat by 5:15am.\n2. Jaisalmer Fort — the golden sandstone turns amber in the last 20 minutes before sunset.\n3. Hampi Virupaksha Temple — eastern entrance catches horizontal morning light perfectly.\n4. Jodhpur Blue City — Mehrangarh Fort casts blue shadows over the old city. 6:30am in winter.\n\n**Technical Settings**\nf/8 for landscape sharpness. ISO 100-200. Bracket +/- 1 stop. Circular polarizer for water reflections.",
     "Pan-India", ["photography", "golden-hour", "travel", "india", "guide"], 13200),
    ("demo_rajan", "road-trip-car-rental-india-guide",
     "Renting a Car in India: The Honest Guide",
     "Indian roads are challenging, chaotic, and exhilarating. Here's how to drive safely and legally.",
     "After driving 180,000+ km across India, here's what rental companies don't tell you.\n\n**International Driving License**\nYour foreign license is valid in India for up to 1 year. An IDP makes checkpoints smoother.\n\n**Insurance Reality**\nMandatory Third Party insurance is included in all rentals. Comprehensive (optional) covers vehicle damage. READ the exclusions — most exclude single-car rollover on mountain roads.\n\n**Mountain Road Rules**\nOn single-lane mountain roads: uphill traffic has right of way. Don't use horn constantly. Night driving above 2,000m is actively dangerous — zero visibility, no guardrails.\n\n**Fuel Strategy**\nAlways fill up in the last major town before National Parks or mountain passes. Ladakh fuel stations are 100-200km apart.",
     "India", ["roadtrip", "india", "driving", "guide", "cars"], 9400),
    ("demo_arjun", "solo-trekking-vs-guided-group",
     "Solo Trekking vs. Guided Group: How to Choose",
     "Both have merit. Here's the honest breakdown from someone who's done both extensively.",
     "There's no correct answer. But there's a correct answer for you, based on experience level, budget, and what you're seeking.\n\n**Solo Trekking Case**\nYou go at your own pace. The acclimatization schedule is entirely yours. You meet locals and other trekkers more naturally. Cost is lower for experienced trekkers with gear.\n\n**The Risks**\nMedical emergencies on solo high-altitude treks kill people every season. AMS, falls, and dehydration can incapacitate you before you can call for help. Solo trekking above 4,000m without a satellite communicator is genuinely dangerous.\n\n**Guided Group Case**\nSafety net, social energy, and logistics handled — permits, food, accommodation, porter management.\n\n**My Recommendation**\nFirst Himalayan trek: always guided. Experience level matters less than altitude familiarity.",
     "Himalayan Region", ["trekking", "solo", "guide", "safety", "himalaya"], 11600),
    ("demo_kavitha", "india-ancient-stepwells-guide",
     "India's Ancient Step Wells: A Traveler's Guide to Vav Architecture",
     "Rani-ki-Vav, Adalaj, Chand Baori — India's step wells are among the world's most extraordinary architectural achievements.",
     "The vav (step well) is one of India's most underappreciated architectural traditions.\n\n**Rani-ki-Vav, Patan (UNESCO)**\nBuilt in 1063 CE by Queen Udaymati. 7 tiers of carved stone descend 28m. The 500 principal sculptures and 1,000 minor ones are in remarkably good condition.\n\n**Chand Baori, Rajasthan**\nThe most photogenic step well in India — 13 levels, 3,500 steps, built in the 9th century. Featured in The Dark Knight Rises.\n\n**Adalaj Vav, Gujarat**\nA synthesis of Hindu and Islamic ornamental traditions. Built in 1498 CE. The five-story well chamber is 65m long with exquisitely carved pavilion stages.",
     "India", ["heritage", "india", "architecture", "stepwells", "culture"], 7600),
    ("demo_sanika", "packing-list-southeast-asia-tropics",
     "The Essential Packing List for Southeast Asia",
     "After 200+ travel days in tropical climates, I've reduced my Southeast Asia kit to 7kg carry-on. Here's the list.",
     "Most first-time Southeast Asia travelers overpack by 8kg.\n\n**Clothing**\n5-7 lightweight synthetic or merino t-shirts. 2 pairs lightweight pants. 1 lightweight down jacket for AC buses (they're freezing). 3 pairs moisture-wicking underwear. 1 pair comfortable sandals + 1 pair walking shoes.\n\n**Health**\nDEET mosquito repellent (30%+ concentration). Oral rehydration salts — buy at Thai pharmacies for INR 20 per sachet. Immodium and antibiotics (get prescription first). Sunscreen SPF 50+.\n\n**Tech**\nPower bank (20,000mAh minimum). Universal adapter. Anti-theft day bag. Offline maps downloaded for all countries.",
     "Southeast Asia", ["packing", "travel", "southeast-asia", "guide", "tips"], 15200),
    ("demo_leila", "hotel-deals-framework",
     "How to Find the Best Hotel Deals: A Framework That Actually Works",
     "Hotel pricing algorithms are sophisticated. Here's how to work with them instead of against them.",
     "After 6 years of booking luxury hotels for clients, I've mapped the pricing patterns most travelers don't know.\n\n**The Tuesday Morning Effect**\nHotel revenue management systems typically review and reset pricing on Monday nights. Tuesday morning is statistically the cheapest time to book, regardless of check-in date.\n\n**Direct Booking vs OTAs**\nOTAs show the best rate prominently. But calling the hotel directly and mentioning you've seen the OTA rate often yields 5-10% discount plus room upgrade. Hotels pay 15-25% commission to OTAs — they strongly prefer direct bookings.\n\n**The 2-Week Rule**\nFor business hotels, cheapest rates are typically 60-120 days out. For leisure resorts, best dynamic pricing windows are 30-45 days before check-in.",
     "Global", ["hotels", "travel-hacks", "luxury", "tips", "booking"], 16800),
    ("demo_elena", "tapas-culture-spain-complete-guide",
     "The Tapas Culture: A Complete Guide to Eating and Drinking in Spain",
     "Tapas are not an appetizer. They are a social institution. Here's how the Spanish actually do it.",
     "Tapas are the misunderstood center of Spanish social life. Most tourists get it wrong.\n\n**The Real Tapas System**\nIn the Basque Country, they're called pintxos and are placed on bar counters — you pick what you want and tell the barman at the end. In Andalusia, some bars still give free tapas with drinks — this survives in Granada and Almeria.\n\n**How Locals Order**\nAt a tapas bar, you do not sit first. You stand at the bar, establish eye contact with the barman, and order directly.\n\n**The Vermouth Hour**\nSaturday at noon is vermut hour. Locals gather at bars for vermouth, olives, and chips.\n\n**Regional Specialties**\nMadrid: patatas bravas, bocadillo de calamares. Barcelona: pan con tomate, croquetas de jamon. Basque: anchoas (anchovies on bread).",
     "Spain", ["spain", "tapas", "food", "culture", "guide"], 10200),
    ("demo_amara", "responsible-safari-tourism-principles",
     "Responsible Safari Tourism: What Every Traveler Should Demand",
     "Not all safaris are equal. Here's how to tell ethical operators from harmful ones before you book.",
     "In 8 years of organizing East African safaris, I've seen both ends of the ethical spectrum.\n\n**The Vehicle Density Problem**\nAt a major lion kill in the Mara, I've counted 47 vehicles surrounding one pride. This causes measurable behavioral changes in big cats. A maximum of 8 vehicles per sighting is the ethical standard.\n\n**Porter Welfare on Kilimanjaro**\nKilimanjaro Porters Assistance Project (KPAP) certification ensures porters are paid fair wages and carry legal loads (maximum 20kg). One-third of Kili operators are non-compliant.\n\n**Community Tourism**\nMaasai community fees go directly to village councils in ethical operations. Mass tourism operators route fees through layers of agents — ask for evidence directly.",
     "East Africa", ["safari", "ethics", "responsible-travel", "africa", "wildlife"], 8700),
    ("demo_kiran", "art-of-solo-travel-guide",
     "The Art of Solo Travel: Everything I've Learned in 10 Years",
     "Solo travel is the best teacher I've encountered. Here's the complete honest guide — fears, logistics, loneliness, and all.",
     "Ten years of solo travel across 40 countries. I have been robbed, food-poisoned, heartbroken, and the most content I've ever been — often on the same trip.\n\n**Loneliness vs Solitude**\nEvery solo traveler confuses these at least once. Loneliness is wishing someone else was there. Solitude is being completely present without needing anyone else.\n\n**The Hostel Myth**\nHostels are primarily for people who want to meet other travelers. A private room in a hostel gives you both privacy and the social common room.\n\n**Safety Fundamentals**\nShare your itinerary with someone at home every 48 hours. Download offline maps. Travel insurance is not optional.\n\n**The Breakthrough Moment**\nEvery solo traveler has a day when everything feels too hard. Getting through that day on your own is transformative in a way no other travel experience is.",
     "Global", ["solo-travel", "guide", "tips", "adventure", "personal-growth"], 14600),
    ("demo_nisha", "rajasthan-shopping-guide",
     "The Rajasthan Shopping Guide: What to Buy, Where, and How to Negotiate",
     "Rajasthan is India's greatest shopping destination. Here's the insider map from someone who's been buying here for 15 years.",
     "Rajasthan produces the finest block-printed textiles, blue pottery, gems, and miniature paintings in India.\n\n**Jaipur**\nBlock printing: Anokhi Museum shop (Amber Road) for certified artisan prints. Johari Bazaar for gems and jewelry — ask for GII graded gemstones if spending more than INR 10,000.\n\n**Jodhpur**\nAntique furniture: dealers around Sojati Gate have genuine antique pieces with documentation. Rajasthali (government emporium) for fixed-price quality baseline.\n\n**Jaisalmer**\nCamel leather goods: bags, journals, and sandals inside and around Jaisalmer Fort at 60% of Delhi prices.\n\n**The Negotiation Principle**\nIn private shops: start at 50%, settle around 65-70%. Government emporiums: fixed price. In markets: 30% reduction typically achievable.",
     "Rajasthan, India", ["rajasthan", "shopping", "guide", "india", "handicrafts"], 12300),
    ("demo_tao", "asia-best-street-food-cities-ranked",
     "Asia's Best Street Food Cities, Ranked",
     "I've eaten my way across 15 Asian cities over 8 years. Here's the definitive ranking with reasoning.",
     "This ranking is based on variety, quality-consistency, value, and the cultural integration of food with daily life.\n\n**1. Penang, Malaysia**\nDensity of world-class dishes within 2km is unmatched. Char Kway Teow, Assam Laksa, Char Siu, and Nasi Kandar all within walking distance. Every stall has decades of history.\n\n**2. Ho Chi Minh City, Vietnam**\nThe 5am food culture. The pho, the banh mi, the broken rice. Diversity within a single city is extraordinary.\n\n**3. Tokyo, Japan**\nStreet food elevated to technical perfection. Standing ramen bars, convenience store onigiri, and 3am yakitori under train tracks.\n\n**4. Bangkok, Thailand**\nEvery taxi driver has a preferred pad thai stall. Volume and accessibility of great food is unmatched in Southeast Asia.\n\n**5. Mumbai, India**\nThe sheer emotional connection of eating bhelpuri on Marine Drive at 9pm makes the city impossible to exclude from any serious list.",
     "Asia", ["food", "asia", "street-food", "ranking", "guide"], 18000),
    ("demo_priya", "india-coastal-gems-undiscovered-beaches",
     "India's Undiscovered Coastal Gems: Beyond Goa and Kerala",
     "India has 7,500km of coastline. Here are the beautiful beaches that haven't been discovered by the tourist circuit yet.",
     "Goa is glorious. Kerala's backwaters are extraordinary. But the undiscovered coastlines are where India's future beach travel is heading.\n\n**Odisha's Coast**\nChangipur, where the sea recedes 5km at low tide, and Konark Beach where the Sun Temple meets the Bay of Bengal. Chilika Lake is the world's second largest coastal lagoon with 160+ bird species.\n\n**Karnataka's Konkan Stretch**\nUdupi district's coastline (Kaup, Someshwar, Maravanthe) combines temples, rivers, and beaches in a 40km stretch with essentially no tourist infrastructure.\n\n**Andhra Pradesh's Coastal Villages**\nRishikonda near Visakhapatnam has the consistent surf break serious surfers are now using. Yarada Beach, accessible only by boat, has no road access and almost zero development.",
     "India", ["coastal", "india", "offbeat", "beaches", "undiscovered"], 10400),
    ("demo_kavitha", "meenakshi-temple-complete-guide",
     "Meenakshi Amman Temple: A Complete Visitor's Guide",
     "There is no temple in South India more overwhelming or more extraordinary. Here's everything you need to navigate it.",
     "The Meenakshi Amman Temple in Madurai has been continuously in use for 2,000 years. It has 33,000 sculptures, 14 gopurams, and 1,500 carved granite pillars.\n\n**Timing**\nArrive at 5:30am for the morning abhishekam (ritual bathing of the deity). The temple opens at 5am. Non-Hindus can attend all areas except the innermost sanctum.\n\n**Navigating the Complex**\nThe temple covers 14 acres. Most visitors see only the main gopurams and Hall of Thousand Pillars. Ask your guide to take you to the Pottramarai Kulam (golden lotus tank) and the small art museum inside the precincts.\n\n**Practical**\nLeave shoes at the official cloak room near the east entrance. Dress modestly — sarongs available for hire. Photography permitted in outer areas.",
     "Madurai, Tamil Nadu", ["temple", "south-india", "culture", "guide", "heritage"], 9100),
    ("demo_arjun", "how-to-fill-your-trip-in-7-days",
     "How to Fill Your Trip in 7 Days",
     "Most hosts panic when they launch a new trip and see empty seats. Here's the exact playbook I use to fill every trip within a week.",
     "After launching 40+ trips on Tapne, I've reduced the filling process to a repeatable system.\n\n**Day 1-2: Price and Title Audit**\nIf you haven't had a single inquiry in 48 hours, your title or price is wrong. Compare 5 similar trips. If yours is 20%+ higher, adjust.\n\n**Day 3: Your Network First**\nMessage your last 10 travelers directly. Personal outreach converts at 40% vs 4% for bulk posts.\n\n**Day 4: Social Proof Sprint**\nPost one piece of content that shows the experience — a video clip, a review screenshot, a behind-the-scenes photo from logistics prep.\n\n**Day 5-7: Create Urgency Legitimately**\nIf 60%+ is filled, mark it. Scarcity is real and should be communicated. If not filled, consider opening an early-bird rate for the first 2 spots.",
     "Host Playbook", ["hosting", "tips", "travel-business", "marketing", "tapne"], 14200),
    ("demo_nisha", "reading-the-room-group-energy-day-one",
     "Reading the Room: Group Energy on Day 1",
     "The first three hours of any group trip determine whether it'll be extraordinary or merely good. Here's what to watch for.",
     "After leading 200+ group experiences, I've learned that Day 1 energy is diagnostic, not accidental.\n\n**The Anchor Guest**\nEvery group has one person who sets the social temperature. Identify them in the first 30 minutes — they're usually the first to laugh, ask questions, or help a stranger.\n\n**The Hesitant Introvert**\nThere's always one. Don't push them into group activities early. Give them a small moment of individual attention on Day 1. They often become the most engaged by Day 3.\n\n**Energy Calibration**\nIf the group is quiet by dinner on Day 1, change the seating arrangement. Shuffle meal groups. A single conversation spark at the right table changes everything.\n\n**What to Never Do**\nForced icebreaker games. They create performance anxiety, not connection. Let the shared experience be the icebreaker.",
     "Host Playbook", ["hosting", "groups", "leadership", "travel-tips", "community"], 5800),
    ("demo_rajan", "pre-trip-whatsapp-group-rules-that-work",
     "The Pre-Trip WhatsApp Group: Rules That Work",
     "A well-run pre-trip WhatsApp group builds anticipation and reduces day-1 logistics chaos. A badly run one creates anxiety.",
     "I've managed 80+ pre-trip WhatsApp groups. Here's the exact structure that works.\n\n**When to Create It**\nExactly 3 weeks before departure. Earlier creates noise. Later creates panic.\n\n**First Message**\nWelcome each person by name. Include: departure point, time, what-to-bring summary, and one sentence about what makes this trip special.\n\n**Rules (Post on Day 1)**\nOnly logistics-critical messages in main group. No good-morning messages. No forwarded content. One dedicated 'questions' thread.\n\n**Day-Before Message**\nThe most important message you'll send. Weather update, packing reminder, meeting point pin, emergency number. Keep it under 150 words.",
     "Host Playbook", ["hosting", "communication", "whatsapp", "logistics", "tips"], 7800),
]

# ── Review templates by trip_type ─────────────────────────────────────────────

REVIEW_TEMPLATES: dict[str, list[tuple[int, str]]] = {
    "trekking": [
        (5, "Absolutely incredible trek. The guide was knowledgeable, views were breathtaking, and logistics were flawless. Ranks top 3 of all treks I've done."),
        (5, "Everything perfectly organized — permits, accommodation, food. The guide's mountain knowledge added so much depth."),
        (5, "Challenging but completely worth it. Reached the summit and felt a wave of emotion I didn't expect."),
        (4, "Great trek overall. Trail exactly as described. Food quality at higher camps could be slightly better but the experience compensated."),
        (4, "Well-organized with a genuinely experienced guide. Itinerary was realistic and we never felt rushed."),
        (4, "Excellent route and logistics. Weather was unpredictable on day 4 but the guide's decision-making kept everyone safe."),
        (3, "Good trek but group size felt large for the summit section. Views were amazing. Day 3 accommodation basic but functional."),
        (5, "Best investment I've made in a travel experience. Physical challenge, natural beauty, and camaraderie made this genuinely life-changing."),
    ],
    "coastal": [
        (5, "A dream coastal escape. Accommodation was right on the water, snorkeling exceptional, and host knows every reef and cove."),
        (5, "Exactly what I needed. Total immersion in a coastal paradise without crowds. Will be back next year."),
        (4, "Beautiful location, great group, well-organized. Kayaking to the sea caves was the highlight."),
        (4, "Exceptional value for experience quality. The beach walk at dawn on Day 2 was magical."),
        (3, "Good experience overall. Snorkeling gear slightly aged but worked fine. Great food and helpful host."),
        (5, "Completely disconnected from work for 5 days and came back a different person. The sunsets justified the trip."),
        (4, "Loved the balance of activity and relaxation. Host's local knowledge made the difference — spots no tourist operator would know."),
    ],
    "food-culture": [
        (5, "Depth of food knowledge was extraordinary. Not just eating but understanding history, technique, and cultural context of every dish."),
        (5, "I've done food tours in 8 countries. This is in the top 2. The host's genuine passion for the cuisine made everything special."),
        (4, "Incredible quantity and quality of food. Stomach capacity was the main limiting factor! The midnight trail was the best part."),
        (4, "Well curated trail with excellent pacing. Every stall felt chosen with care."),
        (5, "Changed the way I think about this cuisine. Learned more in 3 days than in 5 years of cooking."),
        (3, "Good experience. Would have preferred more time at each stop. Food quality was consistently excellent."),
        (4, "The cooking class was worth the trip alone. Market tour that preceded it gave context that made everything make sense."),
    ],
    "culture-heritage": [
        (5, "A revelatory experience. Guide turned what I expected to be a historical tour into a living, breathing story about how civilizations rise and fall."),
        (5, "Extraordinary depth of knowledge from the guide. Every question answered with context and passion. Never felt like a tourist."),
        (4, "Beautifully designed itinerary balancing major sites with hidden gems. Early morning starts worth it for crowd-free experiences."),
        (4, "Excellent pacing. Never felt rushed. Guide's ability to make 1,000-year-old history feel immediate and relevant was remarkable."),
        (3, "Good trip with great sites. Group was large for some narrow heritage passages. Overall experience still very positive."),
        (5, "I've visited temples all my life without understanding what I was seeing. This trip completely changed that."),
        (4, "The sound-and-light show at the main monument was one of the most moving experiences of my travels."),
    ],
    "desert": [
        (5, "The desert at night under a full moon is one of the most transcendent experiences available anywhere on earth."),
        (5, "Camp quality was far beyond expectations. Folk music, fire, stars, and complete silence at midnight. Perfect."),
        (4, "Well organized with genuine culture woven in. The jeep safari at dawn was the highlight."),
        (4, "Excellent food, comfortable camp, knowledgeable guide. Camel ride at sunset was better than any photo could capture."),
        (3, "Great location and atmosphere. Organized cultural performances felt slightly staged but natural desert experience was real."),
        (5, "We saw the Milky Way in full clarity. I've looked up at stars my whole life but never seen the galaxy before this."),
    ],
    "wildlife": [
        (5, "Tiger sightings on both morning drives. Naturalist guide's tracking skills and knowledge of individual tiger territories was remarkable."),
        (5, "Biodiversity was staggering. Even without Big Five, the birds, insects, and smaller mammals made every minute interesting."),
        (4, "Excellent safari logistics and knowledgeable guide. No major predator sighting day 1 but day 2 more than made up for it."),
        (4, "Pre-dawn drives were the most atmospheric. Forest waking up around you is a primal experience that never gets old."),
        (3, "Good safari but accommodation was further from core zone than expected. Drives themselves were excellent."),
        (5, "Wildebeest crossing happened on Day 3. 30 minutes of non-stop drama. I'll carry that image for the rest of my life."),
        (4, "Naturalist guide turned a good safari into a great one. He noticed things we would have missed completely."),
    ],
    "road-trip": [
        (5, "Vehicle was comfortable, driver knowledgeable, and route had surprises around every corner. Perfect pacing."),
        (5, "Road trips reveal a country the way no other travel mode can. This route showed me an India I didn't know existed."),
        (4, "Great itinerary with right balance of driving and exploring. Spontaneous detours the driver suggested were often the best moments."),
        (4, "Well chosen route through dramatic landscapes. Food at roadside dhabas the host recommended was far better than any restaurant."),
        (3, "Enjoyable road trip. Some days felt slightly rushed. Scenery was consistently spectacular throughout."),
        (5, "The motorcycle expedition changed my relationship with travel and with India. 10 days of pure freedom."),
    ],
    "adventure-sports": [
        (5, "The bungee instructor's calm professionalism made me feel completely safe at a moment when my brain was screaming otherwise."),
        (5, "The paragliding views were indescribable. Airborne for 30 minutes over those valleys with no engine noise — absolute peace."),
        (4, "Well organized with excellent safety briefings. Adrenaline levels were exactly as promised."),
        (4, "First time doing any adventure sport. Instructor was patient and made sure I was comfortable at each stage."),
        (5, "Hot air balloon at sunrise was the most beautiful thing I've ever seen. No photo does it justice."),
        (3, "Good adventure experience. Safety standards were clearly high. Weather delay on Day 2 well managed."),
    ],
    "camping": [
        (5, "Camping setup was professional — proper sleeping equipment, good food, guide who made the entire experience feel safe in a remote environment."),
        (5, "Waking up in the forest with nothing but birdsong was the reset my mind needed. Perfect balance of challenge and comfort."),
        (4, "Excellent camping experience. Food quality was unexpectedly high for mountain camping. Great group dynamic."),
        (4, "Night hike to the viewpoint was the highlight. Camping under clear mountain skies with the Milky Way visible."),
        (3, "Good camping trip. Weather challenging on Day 2 but guide managed it well. Overall positive experience."),
        (5, "Everything about this trip was carefully thought through — from campsite selection to route pacing. One of my best travel experiences."),
    ],
    "wellness": [
        (5, "I arrived stressed and exhausted. I left lighter, clearer, and with practices I've continued every day since."),
        (5, "The combination of yoga, Ayurveda, and the natural environment was exactly what I needed. Instructor adapted to the group's range."),
        (4, "Beautiful setting, attentive instruction, and food that made my body feel genuinely nourished."),
        (4, "A genuinely restorative experience. Morning yoga sessions were the highlight of each day."),
        (3, "Good retreat. Yoga was excellent. Some Ayurvedic treatments felt more like add-ons than core to the experience."),
        (5, "Host created a space where I felt completely comfortable going deeper into practices than I normally would."),
    ],
    "city": [
        (5, "Local knowledge this guide brought was extraordinary. Went to places no tourist finds on their own and had some of the best meals of my life."),
        (5, "Perfect city introduction. Balance of iconic sites and neighborhood exploration meant we felt like residents by Day 2."),
        (4, "Excellent itinerary with great local connections. Skip-the-line arrangements saved hours."),
        (4, "Good trip with knowledgeable guide. City came alive in a way it hadn't on previous independent visits."),
        (3, "Enjoyable city trip. Some sites slightly rushed. Evening food walk was the clear highlight."),
        (5, "I've visited this city twice before and never understood it properly. This trip changed that completely."),
        (4, "Hidden neighborhood walk on Day 2 was the best thing we did. No tourist does this — and they're missing the soul of the city."),
    ],
}

# Comment templates
COMMENT_TEMPLATES = [
    "This looks incredible! I've been wanting to do this for years.",
    "Is this trip suitable for someone who has never done this before?",
    "What's the best time of year to join this trip?",
    "Can we customize any part of the itinerary?",
    "How many spots are still available?",
    "I did a similar trip last year and it was life-changing. Highly recommend!",
    "Do you need a visa for this destination? Any complications?",
    "What level of fitness is actually required for this?",
    "I'm traveling solo — is this a good trip for meeting other travelers?",
    "Photos please! Would love to see more from previous trips.",
    "How far in advance should I book?",
    "Is this accessible from multiple cities or only from the starting point?",
    "What's the food situation? Any vegetarian-friendly options?",
    "I have a question about the accommodation — is it shared or private?",
    "This is exactly the kind of trip I've been looking for. Bookmarking this!",
    "Can families with teenagers join this trip?",
]

DM_OPENERS = [
    "Hi! I'm interested in your trip and had a few questions before booking.",
    "Hello! I saw your trip listing and would love to know more about it.",
    "Hi there! Can we talk about the customization options for the trip?",
    "Hello! I'm a solo traveler — would this trip work well for me?",
    "Hi! I've done one of your previous trips and it was amazing. Interested in your new one!",
]

DM_REPLIES = [
    "Of course! Happy to answer any questions. What would you like to know?",
    "Thanks for reaching out! I'd love to have you on the trip.",
    "Great to hear from you! Let me know what you're curious about.",
    "Yes, absolutely! Solo travelers are always welcome on our trips.",
    "Thank you so much! It's always wonderful to have repeat travelers.",
]

TRIP_IMAGE_PALETTES = {
    "city": ((29, 78, 216), (126, 34, 206)),
    "culture-heritage": ((180, 83, 9), (120, 53, 15)),
    "food-culture": ((220, 38, 38), (249, 115, 22)),
    "trekking": ((22, 101, 52), (21, 128, 61)),
    "coastal": ((8, 145, 178), (14, 116, 144)),
    "desert": ((217, 119, 6), (120, 53, 15)),
    "wildlife": ((62, 94, 24), (22, 101, 52)),
    "road-trip": ((55, 65, 81), (15, 23, 42)),
    "camping": ((67, 56, 202), (30, 64, 175)),
    "wellness": ((13, 148, 136), (5, 150, 105)),
    "adventure-sports": ((190, 24, 93), (157, 23, 77)),
}

BLOG_IMAGE_PALETTES = (
    ((37, 99, 235), (30, 64, 175)),
    ((8, 145, 178), (14, 116, 144)),
    ((5, 150, 105), (4, 120, 87)),
    ((234, 88, 12), (194, 65, 12)),
    ((185, 28, 28), (153, 27, 27)),
    ((109, 40, 217), (91, 33, 182)),
)


def _rng(seed_str: str) -> random.Random:
    """Deterministic RNG seeded from a string."""
    seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    return random.Random(seed_int)


def _load_font(size: int, *, bold: bool = False) -> DemoFont:
    font_candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: DemoFont) -> int:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return int(right - left)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: DemoFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = [part for part in str(text or "").split() if part]
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break

    remaining_words = words[len(" ".join(lines + [current]).split()):]
    if remaining_words and len(lines) == max_lines - 1:
        tail = " ".join([current] + remaining_words)
        while tail and _text_width(draw, f"{tail}...", font) > max_width:
            tail = tail.rsplit(" ", 1)[0]
        current = f"{tail}..." if tail else current
    lines.append(current)
    return lines[:max_lines]


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    font: DemoFont,
) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = int(right - left)
    height = int(bottom - top)
    padding_x = 22
    padding_y = 12
    draw.rounded_rectangle(
        (x, y, x + width + (padding_x * 2), y + height + (padding_y * 2)),
        radius=24,
        fill=(255, 255, 255, 42),
        outline=(255, 255, 255, 76),
        width=2,
    )
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill=(255, 255, 255, 235))


def _render_demo_cover(
    *,
    title: str,
    subtitle: str,
    eyebrow: str,
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
) -> bytes:
    width = 1600
    height = 900
    base = Image.new("RGBA", (width, height), primary + (255,))
    draw = ImageDraw.Draw(base, "RGBA")

    for y in range(height):
        blend = y / max(1, height - 1)
        color = tuple(
            int(primary[idx] + ((secondary[idx] - primary[idx]) * blend))
            for idx in range(3)
        )
        draw.line((0, y, width, y), fill=color + (255,))

    accent = tuple(min(255, channel + 28) for channel in secondary)
    draw.ellipse((-180, -140, 720, 760), fill=accent + (70,))
    draw.ellipse((980, 90, 1740, 920), fill=(255, 255, 255, 28))
    draw.rectangle((0, 0, width, height), fill=(6, 10, 24, 58))
    draw.rounded_rectangle((84, 84, 1516, 816), radius=46, outline=(255, 255, 255, 48), width=3)

    eyebrow_font = _load_font(30, bold=True)
    title_font = _load_font(76, bold=True)
    subtitle_font = _load_font(34)

    _draw_pill(draw, x=124, y=120, text=eyebrow, font=eyebrow_font)

    title_lines = _wrap_text(draw, title, font=title_font, max_width=1180, max_lines=3)
    title_y = 270
    for line in title_lines:
        draw.text((124, title_y), line, font=title_font, fill=(255, 255, 255, 246))
        title_y += 92

    subtitle_lines = _wrap_text(draw, subtitle, font=subtitle_font, max_width=1060, max_lines=2)
    subtitle_y = 680
    for line in subtitle_lines:
        draw.text((124, subtitle_y), line, font=subtitle_font, fill=(235, 241, 255, 228))
        subtitle_y += 46

    output = BytesIO()
    base.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


class Command(BaseCommand):
    help = "Seed the Tapne demo catalog with ~70 users, ~70 trips, ~35 blogs, and supporting social/activity data."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe all is_demo=True rows before seeding.")
        parser.add_argument("--confirm", action="store_true", help="Skip interactive confirmation for --reset.")
        parser.add_argument("--verbose", action="store_true", help="Per-record progress output.")
        parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="Print planned actions without writing to DB.")
        parser.add_argument("--skip-social", action="store_true", dest="skip_social", help="Skip follow and bookmark seeding.")
        parser.add_argument("--skip-activity", action="store_true", dest="skip_activity", help="Skip enrollments, reviews, comments, and DMs.")

    def handle(self, *args, **options):
        verbose = options["verbose"]
        dry_run = options["dry_run"]
        skip_social = options["skip_social"]
        skip_activity = options["skip_activity"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB writes will occur."))

        if options["reset"]:
            if not options["confirm"]:
                confirm = input("This will delete ALL is_demo=True rows (trips, blogs, users). Type 'yes' to continue: ")
                if confirm.strip().lower() != "yes":
                    self.stdout.write("Aborted.")
                    return
            if not dry_run:
                self._wipe_demo_rows(verbose)

        with transaction.atomic():
            if dry_run:
                self.stdout.write(f"Would seed {len(HOST_SEEDS)} hosts + {len(TRAVELER_SEEDS)} travelers = {len(HOST_SEEDS) + len(TRAVELER_SEEDS)} users")
                self.stdout.write(f"Would seed {len(TRIP_SEEDS)} trips and {len(BLOG_SEEDS)} blogs")
                return

            users = self._seed_users(verbose)
            trips = self._seed_trips(users, verbose)
            blogs = self._seed_blogs(users, verbose)
            self._seed_trip_media(verbose)
            self._seed_blog_media(verbose)

            if not skip_social:
                self._seed_follows(users, verbose)
                self._seed_bookmarks(users, trips, blogs, verbose)

            if not skip_activity:
                self._seed_enrollments(users, trips, verbose)
                self._seed_reviews(users, trips, blogs, verbose)
                self._seed_comments(users, trips, blogs, verbose)
                self._seed_dms(users, verbose)

        trip_count = Trip.objects.filter(is_demo=True).count()
        blog_count = Blog.objects.filter(is_demo=True).count()
        user_count = AccountProfile.objects.filter(is_demo=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"Demo catalog ready: {user_count} users, {trip_count} trips, {blog_count} blogs."
        ))

    def _wipe_demo_rows(self, verbose: bool) -> None:
        trip_del, _ = Trip.objects.filter(is_demo=True).delete()
        blog_del, _ = Blog.objects.filter(is_demo=True).delete()
        demo_user_ids = list(AccountProfile.objects.filter(is_demo=True).values_list("user_id", flat=True))
        user_del, _ = User.objects.filter(pk__in=demo_user_ids).delete()
        if verbose:
            self.stdout.write(f"Wiped: {trip_del} trips, {blog_del} blogs, {user_del} users")

    def _seed_users(self, verbose: bool) -> dict[str, object]:
        users: dict[str, object] = {}
        all_seeds = [(u, f, l, e, loc, bio) for (u, f, l, e, loc, bio) in HOST_SEEDS]
        traveler_seeds_extended = [(u, f, l, e, loc, "") for (u, f, l, e, loc) in TRAVELER_SEEDS]
        all_seeds += traveler_seeds_extended

        for username, first_name, last_name, email, location, bio in all_seeds:
            user, created = User.objects.update_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                },
            )
            if created:
                user.set_unusable_password()
                user.save()

            AccountProfile.objects.filter(user=user).update(
                is_demo=True,
                location=location,
                bio=bio or f"Travel enthusiast based in {location}.",
                display_name=f"{first_name} {last_name}",
            )

            users[username] = user
            if verbose:
                action = "created" if created else "updated"
                self.stdout.write(f"  User {action}: @{username}")

        return users

    def _seed_trips(self, users: dict[str, object], verbose: bool) -> list[object]:
        now = timezone.now()
        trips: list[object] = []

        for idx, seed in enumerate(TRIP_SEEDS):
            (host_uname, title, trip_type, destination, summary, budget_tier,
             difficulty, pace, group_size, total_seats, price_per_person,
             highlights, included_items, itinerary_titles, faqs, duration_days) = seed

            host = users.get(host_uname)
            if host is None:
                continue

            # Assign status based on index
            if idx < 5:
                status = "draft"
                starts_at = now + timedelta(days=30)
            elif idx < 20:
                status = "completed"
                offset_days = 15 + (idx - 5) * 5
                starts_at = now - timedelta(days=offset_days + duration_days)
            else:
                status = "published"
                offset_days = 7 + ((idx - 20) * 3) % 80
                starts_at = now + timedelta(days=offset_days)

            ends_at = starts_at + timedelta(days=duration_days)

            itinerary_days = [
                {
                    "is_flexible": False,
                    "title": day_title,
                    "description": f"Full day exploring {day_title.lower()} as part of the {title} experience.",
                    "stay": destination,
                    "meals": "Breakfast, Lunch, Dinner",
                    "activities": day_title,
                }
                for day_title in itinerary_titles
            ]

            trip, created = Trip.objects.update_or_create(
                host=host,
                title=title,
                defaults={
                    "summary": summary,
                    "description": f"{summary}\n\nJoin us for an unforgettable journey.",
                    "destination": destination,
                    "trip_type": trip_type,
                    "budget_tier": budget_tier,
                    "difficulty_level": difficulty,
                    "pace_level": pace,
                    "group_size_label": group_size,
                    "total_seats": total_seats,
                    "price_per_person": price_per_person,
                    "highlights": highlights,
                    "included_items": included_items,
                    "itinerary_days": itinerary_days,
                    "faqs": faqs,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "status": status,
                    "is_demo": True,
                    "traffic_score": _rng(title).randint(10, 200),
                },
            )

            trips.append(trip)
            if verbose:
                action = "created" if created else "updated"
                self.stdout.write(f"  Trip {action}: [{status}] {title}")

        return trips

    def _seed_blogs(self, users: dict[str, object], verbose: bool) -> list[object]:
        blogs: list[object] = []
        for (author_uname, slug, title, excerpt, body, location, tags, reads) in BLOG_SEEDS:
            author = users.get(author_uname)
            if author is None:
                continue

            blog, created = Blog.objects.update_or_create(
                slug=slug,
                defaults={
                    "author": author,
                    "title": title,
                    "excerpt": excerpt,
                    "body": body,
                    "location": location,
                    "tags": tags,
                    "reads": reads,
                    "is_published": True,
                    "is_demo": True,
                },
            )

            blogs.append(blog)
            if verbose:
                action = "created" if created else "updated"
                self.stdout.write(f"  Blog {action}: {title[:60]}")

        return blogs

    def _seed_follows(self, users: dict[str, object], verbose: bool) -> None:
        host_usernames = {s[0] for s in HOST_SEEDS}
        traveler_usernames = [s[0] for s in TRAVELER_SEEDS]
        created_count = 0

        for host_uname in host_usernames:
            host_user = users.get(host_uname)
            if host_user is None:
                continue

            rng = _rng(f"follows_{host_uname}")
            followers_sample = rng.sample(
                traveler_usernames,
                k=min(rng.randint(20, 35), len(traveler_usernames)),
            )
            for traveler_uname in followers_sample:
                traveler = users.get(traveler_uname)
                if traveler is None or traveler == host_user:
                    continue
                try:
                    _, created = FollowRelation.objects.get_or_create(
                        follower=traveler,
                        following=host_user,
                    )
                    if created:
                        created_count += 1
                except Exception:
                    pass

        for traveler_uname in traveler_usernames:
            traveler = users.get(traveler_uname)
            if traveler is None:
                continue

            rng = _rng(f"follows_out_{traveler_uname}")
            all_others = [u for k, u in users.items() if k != traveler_uname]
            n = rng.randint(3, 8)
            sample = rng.sample(all_others, k=min(n, len(all_others)))
            for other in sample:
                if other == traveler:
                    continue
                try:
                    _, created = FollowRelation.objects.get_or_create(
                        follower=traveler,
                        following=other,
                    )
                    if created:
                        created_count += 1
                except Exception:
                    pass

        if verbose:
            self.stdout.write(f"  Follows created: {created_count}")

    def _seed_bookmarks(self, users: dict[str, object], trips: list[object], blogs: list[object], verbose: bool) -> None:
        created_count = 0
        user_list = list(users.values())
        trip_ids = [str(t.pk) for t in trips if getattr(t, "status", "") == "published"]  # type: ignore[attr-defined]
        blog_slugs = [getattr(b, "slug", "") for b in blogs if getattr(b, "slug", "")]

        for user in user_list:
            username = str(getattr(user, "username", "") or "")
            rng = _rng(f"bookmarks_{username}")

            trip_sample = rng.sample(trip_ids, k=min(rng.randint(2, 5), len(trip_ids)))
            for trip_id in trip_sample:
                trip = next((t for t in trips if str(getattr(t, "pk", "")) == trip_id), None)
                trip_title = str(getattr(trip, "title", f"Trip #{trip_id}") or "")[:255]
                try:
                    _, created = Bookmark.objects.get_or_create(
                        member=user,
                        target_type="trip",
                        target_key=trip_id,
                        defaults={
                            "target_label": trip_title,
                            "target_url": f"/trips/{trip_id}/",
                        },
                    )
                    if created:
                        created_count += 1
                except Exception:
                    pass

            blog_sample = rng.sample(blog_slugs, k=min(rng.randint(1, 3), len(blog_slugs)))
            for slug in blog_sample:
                blog = next((b for b in blogs if getattr(b, "slug", "") == slug), None)
                blog_title = str(getattr(blog, "title", slug) or "")[:255]
                try:
                    _, created = Bookmark.objects.get_or_create(
                        member=user,
                        target_type="blog",
                        target_key=slug,
                        defaults={
                            "target_label": blog_title,
                            "target_url": f"/blogs/{slug}/",
                        },
                    )
                    if created:
                        created_count += 1
                except Exception:
                    pass

        if verbose:
            self.stdout.write(f"  Bookmarks created: {created_count}")

    def _seed_enrollments(self, users: dict[str, object], trips: list[object], verbose: bool) -> None:
        host_usernames = {s[0] for s in HOST_SEEDS}
        traveler_list = [users[s[0]] for s in TRAVELER_SEEDS if s[0] in users]
        published_trips = [t for t in trips if getattr(t, "status", "") == "published"]
        created_count = 0

        for trip in published_trips:
            host = getattr(trip, "host", None)
            host_id = int(getattr(host, "pk", 0) or 0)
            rng = _rng(f"enroll_{getattr(trip, 'pk', 0)}")
            n = rng.randint(2, 6)
            enrollees = rng.sample(traveler_list, k=min(n, len(traveler_list)))

            for requester in enrollees:
                if int(getattr(requester, "pk", 0) or 0) == host_id:
                    continue
                try:
                    _, created = EnrollmentRequest.objects.get_or_create(
                        trip=trip,
                        requester=requester,
                        defaults={"status": "pending"},
                    )
                    if created:
                        created_count += 1
                except Exception:
                    pass

        if verbose:
            self.stdout.write(f"  Enrollments created: {created_count}")

    def _seed_reviews(self, users: dict[str, object], trips: list[object], blogs: list[object], verbose: bool) -> None:
        traveler_list = [users[s[0]] for s in TRAVELER_SEEDS if s[0] in users]
        completed_trips = [t for t in trips if getattr(t, "status", "") == "completed"]
        created_count = 0

        for trip in completed_trips:
            trip_type = str(getattr(trip, "trip_type", "") or "")
            trip_pk = int(getattr(trip, "pk", 0) or 0)
            target_key = str(trip_pk)
            target_label = str(getattr(trip, "title", "") or "")[:255]
            target_url = f"/trips/{trip_pk}/"

            templates = REVIEW_TEMPLATES.get(trip_type, REVIEW_TEMPLATES["trekking"])
            rng = _rng(f"review_trip_{trip_pk}")
            n = rng.randint(8, 15)
            reviewers = rng.sample(traveler_list, k=min(n, len(traveler_list)))

            for reviewer in reviewers:
                reviewer_uname = str(getattr(reviewer, "username", "") or "")
                tmpl_idx = int(hashlib.md5(f"{trip_pk}_{reviewer_uname}".encode()).hexdigest(), 16) % len(templates)
                rating, body = templates[tmpl_idx]

                try:
                    Review.objects.update_or_create(
                        author=reviewer,
                        target_type="trip",
                        target_key=target_key,
                        defaults={
                            "target_label": target_label,
                            "target_url": target_url,
                            "rating": rating,
                            "headline": f"{'★' * rating} {target_label[:60]}",
                            "body": body,
                        },
                    )
                    created_count += 1
                except Exception:
                    pass

        for blog in blogs:
            blog_slug = str(getattr(blog, "slug", "") or "")
            if not blog_slug:
                continue
            blog_title = str(getattr(blog, "title", "") or "")[:255]
            target_url = f"/blogs/{blog_slug}/"

            rng = _rng(f"review_blog_{blog_slug}")
            n = rng.randint(2, 6)
            reviewers = rng.sample(traveler_list, k=min(n, len(traveler_list)))

            for reviewer in reviewers:
                reviewer_uname = str(getattr(reviewer, "username", "") or "")
                templates = REVIEW_TEMPLATES["culture-heritage"]
                tmpl_idx = int(hashlib.md5(f"{blog_slug}_{reviewer_uname}".encode()).hexdigest(), 16) % len(templates)
                rating, body = templates[tmpl_idx]

                try:
                    Review.objects.update_or_create(
                        author=reviewer,
                        target_type="blog",
                        target_key=blog_slug,
                        defaults={
                            "target_label": blog_title,
                            "target_url": target_url,
                            "rating": rating,
                            "headline": f"{'★' * rating} {blog_title[:60]}",
                            "body": body,
                        },
                    )
                    created_count += 1
                except Exception:
                    pass

        if verbose:
            self.stdout.write(f"  Reviews created: {created_count}")

    def _seed_comments(self, users: dict[str, object], trips: list[object], blogs: list[object], verbose: bool) -> None:
        traveler_list = [users[s[0]] for s in TRAVELER_SEEDS if s[0] in users]
        published_trips = [t for t in trips if getattr(t, "status", "") == "published"]
        created_count = 0

        for trip in published_trips:
            trip_pk = int(getattr(trip, "pk", 0) or 0)
            target_key = str(trip_pk)
            target_label = str(getattr(trip, "title", "") or "")[:255]
            target_url = f"/trips/{trip_pk}/"
            rng = _rng(f"comments_trip_{trip_pk}")
            n = rng.randint(2, 6)
            commenters = rng.sample(traveler_list, k=min(n, len(traveler_list)))

            for commenter in commenters:
                commenter_uname = str(getattr(commenter, "username", "") or "")
                tmpl_idx = int(hashlib.md5(f"{trip_pk}_{commenter_uname}".encode()).hexdigest(), 16) % len(COMMENT_TEMPLATES)
                text = COMMENT_TEMPLATES[tmpl_idx]

                existing = Comment.objects.filter(
                    author=commenter,
                    target_type="trip",
                    target_key=target_key,
                    text__startswith=text[:80],
                ).exists()
                if not existing:
                    try:
                        Comment.objects.create(
                            author=commenter,
                            target_type="trip",
                            target_key=target_key,
                            target_label=target_label,
                            target_url=target_url,
                            text=text,
                        )
                        created_count += 1
                    except Exception:
                        pass

        for blog in blogs[:20]:
            blog_slug = str(getattr(blog, "slug", "") or "")
            if not blog_slug:
                continue
            blog_title = str(getattr(blog, "title", "") or "")[:255]
            target_url = f"/blogs/{blog_slug}/"
            rng = _rng(f"comments_blog_{blog_slug}")
            n = rng.randint(2, 5)
            commenters = rng.sample(traveler_list, k=min(n, len(traveler_list)))

            for commenter in commenters:
                commenter_uname = str(getattr(commenter, "username", "") or "")
                tmpl_idx = int(hashlib.md5(f"{blog_slug}_{commenter_uname}".encode()).hexdigest(), 16) % len(COMMENT_TEMPLATES)
                text = COMMENT_TEMPLATES[tmpl_idx]

                existing = Comment.objects.filter(
                    author=commenter,
                    target_type="blog",
                    target_key=blog_slug,
                    text__startswith=text[:80],
                ).exists()
                if not existing:
                    try:
                        Comment.objects.create(
                            author=commenter,
                            target_type="blog",
                            target_key=blog_slug,
                            target_label=blog_title,
                            target_url=target_url,
                            text=text,
                        )
                        created_count += 1
                    except Exception:
                        pass

        if verbose:
            self.stdout.write(f"  Comments created: {created_count}")

    def _seed_dms(self, users: dict[str, object], verbose: bool) -> None:
        host_list = [users[s[0]] for s in HOST_SEEDS if s[0] in users]
        traveler_list = [users[s[0]] for s in TRAVELER_SEEDS if s[0] in users]
        created_count = 0

        for host in host_list:
            host_id = int(getattr(host, "pk", 0) or 0)
            host_uname = str(getattr(host, "username", "") or "")
            rng = _rng(f"dms_{host_uname}")
            n = rng.randint(3, 6)
            dm_travelers = rng.sample(traveler_list, k=min(n, len(traveler_list)))

            for traveler in dm_travelers:
                traveler_id = int(getattr(traveler, "pk", 0) or 0)
                if traveler_id == host_id:
                    continue

                m1_id = min(host_id, traveler_id)
                m2_id = max(host_id, traveler_id)
                m1 = host if host_id == m1_id else traveler
                m2 = traveler if traveler_id == m2_id else host

                try:
                    thread, t_created = DirectMessageThread.objects.get_or_create(
                        member_one_id=m1_id,
                        member_two_id=m2_id,
                    )
                    if t_created:
                        created_count += 1

                    traveler_uname = str(getattr(traveler, "username", "") or "")
                    opener_idx = int(hashlib.md5(traveler_uname.encode()).hexdigest(), 16) % len(DM_OPENERS)
                    reply_idx = int(hashlib.md5(host_uname.encode()).hexdigest(), 16) % len(DM_REPLIES)

                    opener = DM_OPENERS[opener_idx]
                    reply = DM_REPLIES[reply_idx]

                    if not DirectMessage.objects.filter(thread=thread, sender=traveler, body__startswith=opener[:80]).exists():
                        DirectMessage.objects.create(thread=thread, sender=traveler, body=opener)

                    if not DirectMessage.objects.filter(thread=thread, sender=host, body__startswith=reply[:80]).exists():
                        DirectMessage.objects.create(thread=thread, sender=host, body=reply)

                except Exception:
                    pass

        if verbose:
            self.stdout.write(f"  DM threads created: {created_count}")

    def _seed_trip_media(self, verbose: bool) -> None:
        updated_count = 0

        for trip in Trip.objects.filter(is_demo=True).only("id", "title", "destination", "trip_type", "banner_image"):
            trip_id = int(getattr(trip, "pk", 0) or 0)
            title = str(getattr(trip, "title", "") or "").strip() or f"Tapne Trip {trip_id}"
            destination = str(getattr(trip, "destination", "") or "").strip()
            trip_type = str(getattr(trip, "trip_type", "") or "").strip()
            primary, secondary = TRIP_IMAGE_PALETTES.get(trip_type, ((37, 99, 235), (30, 64, 175)))
            file_name = f"trip_banners/demo/{slugify(title)[:72] or f'trip-{trip_id}'}-{trip_id}.png"

            storage = trip.banner_image.storage
            if not storage.exists(file_name):
                content = _render_demo_cover(
                    title=title,
                    subtitle=destination or "Handpicked Tapne demo itinerary",
                    eyebrow=f"Demo trip • {trip_type.replace('-', ' ') or 'travel'}",
                    primary=primary,
                    secondary=secondary,
                )
                storage.save(file_name, ContentFile(content, name=Path(file_name).name))

            current_name = str(getattr(trip.banner_image, "name", "") or "").strip()
            if current_name != file_name:
                trip.banner_image.name = file_name
                trip.save(update_fields=["banner_image"])
                updated_count += 1

        if verbose:
            self.stdout.write(f"  Trip media updated: {updated_count}")

    def _seed_blog_media(self, verbose: bool) -> None:
        updated_count = 0

        for blog in Blog.objects.filter(is_demo=True).only("id", "slug", "title", "location", "cover_image_url"):
            blog_id = int(getattr(blog, "pk", 0) or 0)
            slug = str(getattr(blog, "slug", "") or "").strip() or f"blog-{blog_id}"
            title = str(getattr(blog, "title", "") or "").strip() or f"Tapne Blog {blog_id}"
            location = str(getattr(blog, "location", "") or "").strip()
            palette_index = int(hashlib.md5(slug.encode("utf-8")).hexdigest(), 16) % len(BLOG_IMAGE_PALETTES)
            primary, secondary = BLOG_IMAGE_PALETTES[palette_index]
            file_name = build_demo_blog_cover_storage_name(slug=slug, blog_id=blog_id)

            if not default_storage.exists(file_name):
                content = _render_demo_cover(
                    title=title,
                    subtitle=location or "Tapne community guide",
                    eyebrow="Demo story • editorial pick",
                    primary=primary,
                    secondary=secondary,
                )
                default_storage.save(file_name, ContentFile(content, name=Path(file_name).name))

            cover_image_url = build_demo_blog_cover_url(slug=slug)
            if str(getattr(blog, "cover_image_url", "") or "").strip() != cover_image_url:
                blog.cover_image_url = cover_image_url
                blog.save(update_fields=["cover_image_url"])
                updated_count += 1

        if verbose:
            self.stdout.write(f"  Blog media updated: {updated_count}")
