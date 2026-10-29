"""The TV tab's shelves: the free old cartoons and films from the Internet Archive, and the words that
sort live channels into news, sports and the rest."""
import glob
import mmap
import os
import re
import urllib.parse
import urllib.request

from .util import fetch_json, item, UA, VIDEO_EXTS
from .screen import video_target


# Cartoons and Free Movies: channels from Plex's free Live TV, picked by name and kind
ANIME_WORDS = ("anime", "animé", "naruto", "one piece", "dragon ball", "pokémon", "pokemon", "sailor moon",
               "gundam", "yu-gi-oh", "hidive", "crunchyroll", "retrocrush", "funimation", "toei", "shonen",
               "shōnen", "manga", "hunter x hunter", "bleach", "inuyasha", "ultraman", "voltron")
TOON_WORDS = ("cartoon", "toon", "animat", "kids", "children", "junior", "nick", "looney", "popeye",
              "scooby", "pink panther", "garfield", "smurf", "teletubbies", "barney", "sesame",
              "power rangers", "transformers", "he-man", "inspector gadget", "care bears", "baby")
CHANNEL_REFRESH = 6 * 3600    # Plex's list of Live TV channels is fetched again after this


def channel_text(c):
    return (c["title"] + " " + c["genre"]).lower()


def is_anime(c):
    return any(w in channel_text(c) for w in ANIME_WORDS)


def is_toon(c):
    return any(w in channel_text(c) for w in TOON_WORDS)


NEWS_WORDS = ("news", "reuters", "bloomberg", "euronews", "france 24", "al jazeera", "weather",
              "c-span", "cheddar", "politic")
SPORT_WORDS = ("sport", "nfl", "nba", "mlb", "nhl", "golf", "tennis", "soccer", "football", "fútbol",
               "racing", "motor", "boxing", "wrestling", "fight", "ufc", "mma", "olympic", "fubo",
               "stadium", "pbr", "rodeo", "poker", "billiard", "surf", "skate", "fishing", "hunting",
               "outdoor", "cycling", "rugby", "cricket", "hockey", "baseball", "basketball",
               "volleyball", "lacrosse", "red bull")


def is_news(c):
    return any(w in channel_text(c) for w in NEWS_WORDS)


def is_sport(c):
    return any(w in channel_text(c) for w in SPORT_WORDS)


def live_pick(what, c):
    """Whether a Plex Live TV channel belongs in a list: anime, toons, movies, news or sports."""
    if what == "anime":
        return is_anime(c)
    if what == "toons":
        return is_toon(c) and not is_anime(c)
    if what == "movies":
        return "movie" in c["genre"].lower()
    if what == "news":
        return is_news(c)
    if what == "sports":
        return is_sport(c)
    return False


def channel_row(c):
    return dict(item("plexlive:" + c["key"], c["title"], "live", "plexlive:" + c["key"], sub=c["genre"]),
                thumb=None, ptype="channel")


# Old cartoons from the Internet Archive, built in so Cartoons opens at once: no
# searching the Archive. Each streams from archive.org when you play it.
#   folder | title | year | archive.org item | the file in it
# (add more the same way: the item is the last part of its archive.org/details/... link)
CLASSIC_TOONS = """
Popeye | I'm in the Army Now | 1936 | im_in_the_army_now | im_in_the_army_now_512kb.mp4
Popeye | Little Swee'Pea | 1936 | little-sweepea-1936 | Little Swee'pea (1936).mp4
Popeye | Popeye the Sailor Meets Sindbad the Sailor | 1936 | Popeye_meetsSinbadtheSailor | Popeye_meetsSinbadtheSailor_512kb.mp4
Popeye | I Never Changes My Altitude | 1937 | MorePopeyeCartoons | INeverChangesMyAltitude_512kb.mp4
Popeye | Popeye the Sailor Meets Ali Baba's Forty Thieves | 1937 | PopeyeAliBaba | PopeyeAliBaba_512kb.mp4
Popeye | The Paneless Window Washer | 1937 | Popeye_ThePanelessWindowWasher | Popeye_ThePanelessWindowWasher_512kb.mp4
Popeye | A Date to Skate | 1938 | MorePopeyeCartoons | ADateToSkate_512kb.mp4
Popeye | Aladdin and His Wonderful Lamp | 1939 | Popeye_the_Sailor_Meets_Aladdin_and_His_Wonderful_Lamp | Popeye_-_Aladdin_and_His_Wonderful_Lamp_512kb.mp4
Popeye | Customers Wanted | 1939 | customers_wanted | customers_wanted_512kb.mp4
Popeye | Me Musical Nephews | 1942 | popeye-pubdomain | Me-Musical-Nephews.mp4
Popeye | Big Bad Sindbad | 1952 | AHaulInOne1956 | Big Bad Sindbad (1952).mp4
Popeye | Shuteye Popeye | 1952 | popeye_shuteye_popeye | popeye_shuteye_popeye_512kb.mp4
Popeye | Ancient Fistory | 1953 | popeye_the_sailor_ancient_fantasy | popeye_the_sailor_ancient_fantasy_512kb.mp4
Popeye | Bride and Gloom | 1954 | Popeye_BrideandGloom | Popeye_BrideandGloom_512kb.mp4
Popeye | Floor Flusher | 1954 | Popeye_Floor_Flusher_1954 | Popeye_Floor_Flusher_512kb.mp4
Popeye | Fright to the Finish | 1954 | popeye_fright_to_the_finish | popeye_fright_to_the_finish_512kb.mp4
Popeye | Gopher Spinach | 1954 | Popeye_Gopher_Spinach_1954 | Popeye_Gopher_Spinach_512kb.mp4
Popeye | Greek Mirthology | 1954 | Popeye_Greek_Mirthology_1954 | Popeye_Greek_Mirthology_512kb.mp4
Popeye | Popeye's 20th Anniversary | 1954 | MorePopeyeCartoons | Popeyes20thAnniversary_512kb.mp4
Popeye | Private Eye Popeye | 1954 | popeye_private_eye_popeye | popeye_private_eye_popeye_512kb.mp4
Popeye | Taxi-Turvy | 1954 | popeye_taxi-turvey | popeye_taxi-turvey_512kb.mp4
Popeye | Cookin' with Gags | 1955 | Popeye_Cooking_With_Gags_1954 | Popeye_Cookin_with_Gags_512kb.mp4
Popeye | A Haul in One | 1956 | AHaulInOne1956 | A Haul in One (1956).mp4
Popeye | Assault and Flattery | 1956 | Popeye_Assault_and_Flattery_1956 | Popeye_Assault_and_Flattery_512kb.mp4
Popeye | I Don't Scare | 1956 | popeye_i_dont_scare | popeye_i_dont_scare_512kb.mp4
Popeye | Insect to Injury | 1956 | insect_to_injury | insect_to_injury_512kb.mp4
Popeye | Out to Punch | 1956 | Popeye_Out_of_the_Punch_1956 | Popeye_Out_To_Punch_1956_512kb.mp4
Popeye | Parlez Vous Woo | 1956 | Popeye_Parlez_Vous_Woo_1956 | Popeye_Parlez_Vous_Woo_1956_512kb.mp4
Popeye | Popeye for President | 1956 | Popeye_forPresident | Popeye_forPresident_512kb.mp4
Popeye | Nearlyweds | 1957 | Popeye_Nearlyweds | Popeye_Nearlyweds_512kb.mp4
Popeye | Patriotic Popeye | 1957 | popeye_patriotic_popeye | popeye_patriotic_popeye_512kb.mp4
Popeye | Spooky Swabs | 1957 | MorePopeyeCartoons | SpookySwabs_512kb.mp4
Popeye | Spree Lunch | 1957 | spree_lunch | spree_lunch_512kb.mp4
Popeye | The Crystal Brawl | 1957 | MorePopeyeCartoons | TheCrystalBrawl_512kb.mp4
Looney Tunes | Bosko the Doughboy | 1931 | bosko-the-doughboy-1931_202305 | Bosko the Doughboy (1931).mp4
Looney Tunes | Ups 'n Downs | 1931 | ups-n-downs-1931 | Ups 'n Downs (1931).mp4
Looney Tunes | Yodeling Yokels | 1931 | yodeling-yokels-1931 | Yodeling Yokels (1931).mp4
Looney Tunes | Battling Bosko | 1932 | BattlingBosko1931HughHarmanRudolfIsing | Battling Bosko 1931 Hugh Harman, Rudolf Ising .mp4
Looney Tunes | Get Rich Quick Porky | 1937 | get-rich-quick-porky-1937 | Get Rich Quick Porky (1937).mp4
Looney Tunes | Porky's Railroad | 1937 | PorkysRailroad_48 | 1937-porkyPig-PorkysRailroad.mp4
Looney Tunes | Daffy Duck and the Dinosaur | 1939 | DaffyDuckAndTheDinosaur1939_201707 | Daffy Duck and the Dinosaur (1939).mp4
Looney Tunes | Prest-O Change-O | 1939 | prest-o-change-o-1939 | Prest-O Change-O (1939).mp4
Looney Tunes | Robin Hood Makes Good | 1939 | robin-hood-makes-good-1939 | Robin Hood Makes Good (1939).mp4
Looney Tunes | A Coy Decoy | 1941 | a-coy-decoy-1941 | A Coy Decoy (1941).mp4
Looney Tunes | Notes to You | 1941 | notes-to-you-1941 | Notes to You (1941).mp4
Looney Tunes | Porky's Ant | 1941 | porkys-ant-1941 | Porky's Ant (1941).mp4
Looney Tunes | Porky's Bear Facts | 1941 | porkys-bear-facts-1941 | Porky's Bear Facts (1941).mp4
Looney Tunes | Porky's Preview | 1941 | porkys-preview-1941 | Porky's Preview (1941).mp4
Looney Tunes | Porky's Prize Pony | 1941 | porkys-prize-pony-1941 | Porky's Prize Pony (1941).mp4
Looney Tunes | The Henpecked Duck | 1941 | the-henpecked-duck-1941 | The Henpecked Duck (1941).mp4
Looney Tunes | We, the Animals Squeak! | 1941 | we-the-animals-squeak-1941 | We, the Animals Squeak! (1941).mp4
Looney Tunes | A Tale of Two Kitties | 1942 | a-tale-of-two-kitties-1942_202304 | A Tale of Two Kitties (1942).mp4
Looney Tunes | Case of the Missing Hare | 1942 | case-of-the-missing-hare-1942 | Case of the Missing Hare (1942).mp4
Looney Tunes | Fox Pop | 1942 | fox-pop-1942 | Fox Pop (1942).mp4
Looney Tunes | Fresh Hare | 1942 | fresh-hare-1942 | Fresh Hare (1942).mp4
Looney Tunes | Porky's Cafe | 1942 | porkys-cafe-1942 | Porky's Cafe (1942).mp4
Looney Tunes | Porky's Pastry Pirates | 1942 | porkys-pastry-pirates-1942 | Porky's Pastry Pirates (1942).mp4
Looney Tunes | The Daffy Duckaroo | 1942 | TheDaffyDuckaroo_109 | TheDaffyDuckaroo.mp4
Looney Tunes | The Dover Boys at Pimento University | 1942 | the-dover-boys-at-pimento-university-or-the-rivals-of-roquefort-hall | The Dover Boys at Pimento University or The Rivals of Roquefort Hall.mp4
Looney Tunes | The Ducktators | 1942 | DucktatorsWwii | 08-TheDucktators_512kb.mp4
Looney Tunes | The Impatient Patient | 1942 | the-impatient-patient-1942 | The Impatient Patient (1942).mp4
Looney Tunes | The Wabbit Who Came to Supper | 1942 | the-wabbit-who-came-to-supper-1942 | The Wabbit Who Came to Supper (1942).mp4
Looney Tunes | The Wacky Wabbit | 1942 | the-wacky-wabbit-1942 | The Wacky Wabbit (1942).mp4
Looney Tunes | A Corny Concerto | 1943 | ACornyConcerto1943BugsBunny | ACornyConcerto1943BugsBunnyDaffyDuckElmerFudd-m735o_eewgg.mp4
Looney Tunes | Confusions of a Nutzy Spy | 1943 | ConfusionsOfANutzySpy1943 | Confusions of a Nutzy Spy (1943)-b0uVtS7nrCA.mp4
Looney Tunes | Daffy - The Commando | 1943 | DaffyDuckAndTheDinosaur1939_201707 | Daffy the Commando (1943).mp4
Looney Tunes | Falling Hare | 1943 | falling-hare-1943 | Falling Hare (1943).mp4
Looney Tunes | Pigs in a Polka | 1943 | pigs-in-a-polka-1943 | Pigs in a Polka (1943).mp4
Looney Tunes | Porky Pig's Feat | 1943 | porky-pigs-feat-1943 | Porky Pig's Feat (1943).mp4
Looney Tunes | Scrap Happy Daffy | 1943 | scraphappydaffy | scraphappydaffy.mp4
Looney Tunes | The Fifth-Column Mouse | 1943 | the-fifth-column-mouse-1943 | The Fifth-Column Mouse (1943).mp4
Looney Tunes | To Duck or Not to Duck | 1943 | DaffyDuckAndTheDinosaur1939_201707 | To Duck or not To Duck (1943).mp4
Looney Tunes | Wackiki Wabbit | 1943 | wackiki-wabbit-1943 | Wackiki Wabbit (1943).mp4
Looney Tunes | Yankee Doodle Daffy | 1943 | yankee-doodle-daffy-1943_202304 | Yankee Doodle Daffy (1943).mp4
Superman | The Mad Scientist | 1941 | superman_the_mad_scientist | Superman-01-The_Mad_Scientist_512kb.mp4
Superman | The Mechanical Monsters | 1941 | superman_the_mechanical_monsters | superman_the_mechanical_monsters_512kb.mp4
Superman | Billion Dollar Limited | 1942 | superman_billion_dollar_limited | billion_dollar_limited.mp4
Superman | Destruction, Inc. | 1942 | superman_destruction_inc | Superman-13-Destruction_Inc_512kb.mp4
Superman | Electric Earthquake | 1942 | superman_electric_earthquake | superman_electric_earthquake_512kb.mp4
Superman | Eleventh Hour | 1942 | superman_eleventh_hour | superman_eleventh_hour_512kb.mp4
Superman | Japoteurs | 1942 | japoteurs | japoteurs_512kb.mp4
Superman | Showdown | 1942 | showdown | showdown_512kb.mp4
Superman | Terror on the Midway | 1942 | superman_terror_on_the_midway | Superman-09-Terror_on_the_Midway_512kb.mp4
Superman | The Arctic Giant | 1942 | arctic_giant | arctic_giant_512kb.mp4
Superman | The Bulleteers | 1942 | bulleteers | bulleteers_512kb.mp4
Superman | The Magnetic Telescope | 1942 | magnetic_telescope | magnetic_telescope_512kb.mp4
Superman | Volcano | 1942 | superman_volcano | Superman-08-Volcano_512kb.mp4
Superman | Jungle Drums | 1943 | jungle_drums | jungle_drums_512kb.mp4
Superman | Secret Agent | 1943 | secret_agent | secret_agent_512kb.mp4
Superman | The Mummy Strikes | 1943 | mummy_strikes | mummy_strikes_512kb.mp4
Superman | The Underground World | 1943 | superman_underground_world | Superman-16-The_Underground_World_512kb.mp4
Betty Boop | Bamboo Isle | 1932 | bb_bamboo_isle | bb_bamboo_isle_512kb.mp4
Betty Boop | Betty Boop for President | 1932 | Betty_Boop_for_President_1932 | Betty_Boop_for_President_1932_512kb.mp4
Betty Boop | Chess-Nuts | 1932 | bb_chess_nuts | bb_chess_nuts_512kb.mp4
Betty Boop | Minnie the Moocher | 1932 | bb_minnie_the_moocher | bb_minnie_the_moocher_512kb.mp4
Betty Boop | Betty Boop's Big Boss | 1933 | bb_big_boss | bb_big_boss_512kb.mp4
Betty Boop | Betty Boop's Crazy Inventions | 1933 | Betty_Boops_Crazy_Inventions_1933 | Betty_Boops_Crazy_Inventions_1933_512kb.mp4
Betty Boop | Betty Boop's Ker-Choo | 1933 | BettyBoopCartoons | Betty_Boops_KerCho_1932_512kb.mp4
Betty Boop | I Heard | 1933 | BettyBoop-IHeared1932 | BettyBoop-IHeared1932._512kb.mp4
Betty Boop | Is My Palm Read? | 1933 | BettyBoopCartoons | Betty_Boop_Is_My_Palm_Read_1932_512kb.mp4
Betty Boop | Morning, Noon and Night | 1933 | bb_morning_noon_and_night | bb_morning_noon_and_night_512kb.mp4
Betty Boop | Mother Goose Land | 1933 | Betty_Boop_Mother_Goose_Land_1933 | Betty_Boop_Mother_Goose_Land_1933_512kb.mp4
Betty Boop | Parade of the Wooden Soldiers | 1933 | bb_parade_of_the_wooden_soldiers | bb_parade_of_the_wooden_soldiers_512kb.mp4
Betty Boop | Snow White | 1933 | bb_snow_white | bb_snow_white_512kb.mp4
Betty Boop | The Old Man of the Mountain | 1933 | bb_old_man_of_the_mountain | bb_old_man_of_the_mountain_512kb.mp4
Betty Boop | Betty Boop's Rise to Fame | 1934 | bb_rise_to_fame | bb_rise_to_fame_512kb.mp4
Betty Boop | Betty in Blunderland | 1934 | bb_betty_in_blunderland | bb_betty_in_blunderland_512kb.mp4
Betty Boop | A Language All My Own | 1935 | Betty_Boop_a_Language_All_My_Own_1935 | Betty_Boop_a_Language_All_My_Own_1935_512kb.mp4
Betty Boop | Baby Be Good | 1935 | Betty_Boop_Baby_Be_Good_1935 | Betty_Boop_Baby_Be_Good_1935_512kb.mp4
Betty Boop | Betty Boop and Grampy | 1935 | bb_and_grampy | bb_and_grampy_512kb.mp4
Betty Boop | Betty Boop with Henry | 1935 | Betty_Boop_with_Henry_1935 | Betty_Boop_with_Henry_1935_512kb.mp4
Betty Boop | Judge for a Day | 1935 | Betty_Boop_Judge_For_a_Day_1935 | Betty_Boop_Judge_For_a_Day_1935_512kb.mp4
Betty Boop | Stop That Noise | 1935 | bb_stop_that_noise | bb_stop_that_noise_512kb.mp4
Betty Boop | Swat the Fly | 1935 | bb_swat_the_fly | bb_swat_that_fly_512kb.mp4
Betty Boop | A Song a Day | 1936 | BettyBoopCartoons | Betty_Boop_A_Song_a_Day_1936_512kb.mp4
Betty Boop | Betty Boop and Little Jimmy | 1936 | Betty_Boop_and_Little_Jimmy_1936 | Betty_Boop_and_Little_Jimmy_1936_512kb.mp4
Betty Boop | Betty Boop and the Little King | 1936 | bb_and_the_little_king | bb_and_the_little_king_512kb.mp4
Betty Boop | Happy You and Merry Me | 1936 | bb_happy_you | bb_happy_you_512kb.mp4
Betty Boop | More Pep | 1936 | BettyBoopCartoons | Betty_Boop_More_Pep_1936_512kb.mp4
Betty Boop | Not Now | 1936 | bb_not_now | bb_not_now_512kb.mp4
Betty Boop | Training Pigeons | 1936 | Betty_Boop_Training_Pigeons_1936 | Betty_Boop_Training_Pigeons_1936_512kb.mp4
Betty Boop | House Cleaning Blues | 1937 | bb_house_cleaning_blues | bb_house_cleaning_blues_512kb.mp4
Betty Boop | The Candid Candidate | 1937 | BettyBoopCartoons | The_Candid_Candidate_1937_512kb.mp4
Betty Boop | The Impractical Joker | 1937 | bb_the_impractical_joker | bb_the_impractical_joker_512kb.mp4
Betty Boop | Whoops! I'm a Cowboy | 1937 | Betty_Boop_Whoops_Im_a_Cowboy_1937 | Whoops_Im_a_Cowboy_1937_512kb.mp4
Betty Boop | Musical Mountaineers | 1939 | bb_musical_mountaineers | bb_musical_mountaineers_512kb.mp4
Betty Boop | The Scared Crows | 1939 | Betty_Boop_The_Scared_Crows_1939 | Betty_Boop_The_Scared_Crows_1939_512kb.mp4
Casper & friends | Little Lulu: Lulu's Birthday Party | 1944 | 1944LulusBirthdayParty | 1944-12-29 Lulu's Birthday Party.mp4
Casper & friends | The Friendly Ghost | 1945 | TheFriendlyGhost | TheFriendlyGhost_512kb.mp4
Casper & friends | Little Lulu: Bargain Counter Attack | 1946 | littlelulu-publicdomain | Bargain Counter Attack (1946).mp4
Casper & friends | Little Lulu: Bored of Education | 1946 | littlelulu-publicdomain | Bored of Education (1946).mp4
Casper & friends | Little Lulu: Chick and Double Chick | 1946 | littlelulu-publicdomain | Chick and Double Chick (1946).mp4
Casper & friends | Herman: Naughty But Mice | 1947 | herman-the-mouse-naughty-but-mice | Herman the Mouse - Naughty But Mice.mp4
Casper & friends | Little Lulu: A Bout with a Trout | 1947 | littlelulu-publicdomain | A Bout with a Trout (1947).mp4
Casper & friends | Little Lulu: Cad and Caddy | 1947 | littlelulu-publicdomain | Cad and Caddy (1947).mp4
Casper & friends | Little Lulu: Musica-Lulu | 1947 | littlelulu-publicdomain | Musica-Lulu (1947).mp4
Casper & friends | Little Lulu: Super Lulu | 1947 | littlelulu-publicdomain | Super Lulu (1947).mp4
Casper & friends | Little Audrey: Butterscotch and Soda | 1948 | LittleAudreyInbutterscotchAndSoda1948 | ButterscotchAndSoda_512kb.mp4
Casper & friends | Little Lulu: The Dog Show-Off | 1948 | littlelulu-publicdomain | The Dog Show-Off (1948).mp4
Casper & friends | Screen Song: Little Brown Jug | 1948 | paramounts-screen-songs-the-famous-studios-collection-1948-50 | Screen Songs - Little Brown Jug (1948).mp4
Casper & friends | There's Good Boos To-Night | 1948 | noveltoon_casper_tfg_theres_good_boos_tonight | noveltoon_casper_tfg_theres_good_boos_tonight_512kb.mp4
Casper & friends | A Haunting We Will Go | 1949 | noveltoons-a-haunting-we-will-go-1949-philip-loro-print | Casper the Ghost & Friends 03. A Haunting We Will Go (1949, Famous Studios).mp4
Casper & friends | Little Audrey: The Lost Dream | 1949 | Little_Audrey_The_Lost_Dream_1949 | Little_Audrey_The_Lost_Dream_512kb.mp4
Casper & friends | Noveltoon: Hep Cat Symphony | 1949 | HepCatSymphony | HepCatSymphony_512kb.mp4
Casper & friends | Screen Song: Toys Will Be Toys | 1949 | paramounts-screen-songs-the-famous-studios-collection-1948-50 | Screen Songs - Toys Will Be Toys (1949).mp4
Casper & friends | Little Audrey: Goofy Goofy Gander | 1950 | little_audry_goofy_goofy_gander | little_audry_goofy_goofy_gander_512kb.mp4
Casper & friends | Little Audrey: Tarts and Flowers | 1950 | noveltoon_tarts_and_flowers | noveltoon_tarts_and_flowers_512kb.mp4
Mighty Mouse & Terrytoons | Caviar | 1930 | All-30s-Terrytoon-Cartoons | 30.02.23 Caviar.mp4
Mighty Mouse & Terrytoons | Golf Nuts | 1930 | All-30s-Terrytoon-Cartoons | 30.12.14 Golf Nuts.mp4
Mighty Mouse & Terrytoons | Pretzels | 1930 | All-30s-Terrytoon-Cartoons | 30.03.09 Pretzels.mp4
Mighty Mouse & Terrytoons | Billy Mouse's Akwakade | 1940 | 1940publicdomainanimation | 1940.08.09 - Billy Mouse's Akwakade.mp4
Mighty Mouse & Terrytoons | Mighty Mouse: Wolf! Wolf! | 1944 | mighty_mouse_wolf_wolf | mighty_mouse_wolf_wolf_512kb.mp4
Mighty Mouse & Terrytoons | Heckle and Jeckle: The Talking Magpies | 1946 | the-talking-magpies-1946 | The Talking Magpies (1946).mp4
Woody Woodpecker & Lantz | Oswald: Permanent Wave | 1929 | oswald-collection | 54 - Permanent Wave (Lantz, 1929).mp4
Woody Woodpecker & Lantz | Oswald: Snow Use | 1929 | oswald-collection | 57 - Snow Use (Lantz, 1929).mp4
Woody Woodpecker & Lantz | Oswald: Henpecked | 1930 | oswald-collection | 78 - Henpecked (Lantz, 1930).mp4
Woody Woodpecker & Lantz | Oswald: My Pal Paul | 1930 | oswald-collection | 74 - My Pal Paul (Lantz, 1930).mp4
Woody Woodpecker & Lantz | Oswald: Spooks | 1930 | oswald-collection | 76 - Spooks (Lantz, 1930).mp4
Woody Woodpecker & Lantz | Boy Meets Dog! | 1938 | Boy_Meets_Dog_1938 | Boy_Meets_Dog_1938_512kb.mp4
Woody Woodpecker & Lantz | Woody Woodpecker: Pantry Panic | 1941 | woody_woodpecker_pantry_panic | woody_woodpecker_pantry_panic_512kb.mp4
Woody Woodpecker & Lantz | Andy Panda: Canine Commandos | 1943 | CanineCommandos | CanineCommandos.mp4
Color Classics | Poor Cinderella | 1934 | Betty_Boop_Poor_Cinderella_1934 | Betty_Boop_Poor_Cinderella_1934_512kb.mp4
Color Classics | The Little Dutch Mill | 1934 | 1934ParamountFleischerStudiosColorClassicsCartoonLittleDutchMillwalterLantzMaxFleischer | 1934-paramount-fleischerStudios-colorClassicsCartoon-LittleDutchMillwalterLantzMaxFleischer.mp4
Color Classics | The Song of the Birds | 1935 | TheSongOfTheBirds-1935 | CC-The_Song_Of_The_Birds-512K_512kb.mp4
Color Classics | Somewhere in Dreamland | 1936 | 1936_20240806 | Somewhere in Dreamland (1936) Color Classic.mp4
Color Classics | The Little Stranger | 1936 | TheLittleStranger1936 | Color_Classics-The_Little_Stranger-256K_512kb.mp4
Color Classics | A Car-Tune Portrait | 1937 | ACarTunePortrait-1937 | CC-A_Car-Tune_Portrait-512K_512kb.mp4
Color Classics | Educated Fish | 1937 | EducatedFish-1937 | CC-Educated_Fish-512K_512kb.mp4
Color Classics | Hunky and Spunky | 1938 | hunky-and-spunky | Hunky and Spunky (1938).mp4
Color Classics | The Playful Polar Bears | 1938 | ThePlayfulPolarBears-1938 | CC-The_Playful_Polar_Bears-512K_512kb.mp4
Color Classics | Small Fry | 1939 | SmallFry-1939 | CC-Small_Fry-512K_512kb.mp4
Color Classics | The Barnyard Brat | 1939 | hunky-and-spunky | The Barnyard Brat (1939).mp4
Color Classics | A Kick in Time | 1940 | hunky-and-spunky | A Kick in Time (1940).mp4
Color Classics | Little Lambkins | 1940 | LittleLambkins-1940 | CC-Little_Lambkins-512K_512kb.mp4
Color Classics | Snubbed by a Snob | 1940 | hunky-and-spunky | Snubbed by a Snob (1940).mp4
Felix & silents | Krazy Kat Goes A-Wooing | 1916 | Krazy_kat_goesA-wooing_1916 | Krazy_Kat_goes_a-wooing_1916_512kb.mp4
Felix & silents | Krazy Kat: Bugologist | 1916 | Krazy_Kat_Bugolist_1916 | Krazy_Kat_bugolist_1916_512kb.mp4
Felix & silents | Out of the Inkwell: Invisible Ink | 1921 | InvisibleInkDaveFleischer1921 | Invisible Ink (Dave Fleischer, 1921) .mp4
Felix & silents | Out of the Inkwell: Bubbles | 1922 | KokoInBubbles | OutOfTheInkwell-KokoBubblesmaxFleischer1922.mp4
Felix & silents | Alice Comedies: Alice Loses Out | 1925 | silent-alice-loses-out | Alice Loses Out.mp4
Felix & silents | Felix the Cat: Felix All Puzzled | 1925 | FelixAllPuzzled1925 | Felix All Puzzled [1925].mp4
Felix & silents | Felix the Cat: Germ Mania | 1927 | FelixGermMania1927 | Felix Germ Mania [1927].mp4
Felix & silents | Felix the Cat: The Non-Stop Fright | 1927 | FelixTheCat-TheNonStopFright1927 | FelixTheCatInNonStopFright1927_512kb.mp4
Felix & silents | Oswald the Lucky Rabbit: Trolley Troubles | 1927 | WaltDisney1927OSWALDTHELUCKYRABBITTROLLEYTROUBLESXvid | Walt Disney 1927 - OSWALD THE LUCKY RABBIT - TROLLEY TROUBLES_xvid.mp4
Felix & silents | Felix the Cat: Comicalamities | 1928 | FelixComicalamities1928 | Felix Comicalamities [1928].mp4
Felix & silents | Inkwell Imps: KoKo's Earth Control | 1928 | out-of-the-inkwell-cartoon-collection | Inkwell Imps _ KoKo's Earth Control _ 1928 (480p_30fps_H264-128kbit_AAC).mp4
Felix & silents | Mickey Mouse: Plane Crazy (silent version) | 1928 | disneycartoons-publicdomain | Plane Crazy (1928, silent version).mp4
Felix & silents | Mickey Mouse: Steamboat Willie | 1928 | steamboat-willie-mickey | 01 - Steamboat Willie.mp4
Felix & silents | Mickey Mouse: The Gallopin' Gaucho | 1928 | disneycartoons-publicdomain | The Gallopin' Gaucho (1928).mp4
Felix & silents | Oswald the Lucky Rabbit: Oh What a Knight | 1928 | WaltDisney1927OSWALDTHELUCKYRABBITTROLLEYTROUBLESXvid | Oswald the Lucky Rabbit ~ Oh What a Knight.mp4
Felix & silents | Felix the Cat: Felix Woos Whoopee | 1930 | FelixWoosWhoopee1930 | Felix Woos Whoopee [1930].mp4
Felix & silents | Felix the Cat: Bold King Cole | 1936 | all-van-beuren-cartoons-1921-1936 | Felix_BoldKingCole_512kb.mp4
Felix & silents | Felix the Cat: The Goose That Laid the Golden Egg | 1936 | felix_the_cat_the_goos_that_laid_the_golden_egg | felix_the_cat_the_goos_that_laid_the_golden_egg_512kb.mp4
Flip the Frog & Iwerks | Flip the Frog: Fiddlesticks | 1930 | FLIP_FROG-FIDDLESTICKS | FLIP_FROG-FIDDLESTICKS_DVD_512kb.mp4
Flip the Frog & Iwerks | Flip the Frog: Africa Squeaks | 1931 | AfricaSqueaks1931UbIwerksSoundCartoon | AfricaSqueaks1931UbIwerksSoundCartoon.mp4
Flip the Frog & Iwerks | Flip the Frog: Jail Birds | 1931 | JailBirds1931UbIwerksSoundCartoon | JailBirds1931UbIwerksSoundCartoon.mp4
Flip the Frog & Iwerks | Flip the Frog: Laughing Gas | 1931 | flip-the-frog-ub-iwerks-1930-33 | Laughing Gas (1931) Flip the Frog.mp4
Flip the Frog & Iwerks | Flip the Frog: Spooks | 1931 | flip-the-frog-ub-iwerks-1930-33 | Spooks (1931) Flip the Frog.mp4
Flip the Frog & Iwerks | Flip the Frog: The Office Boy | 1932 | TheOfficeBoy1932UbIwerksSoundCartoon | TheOfficeBoy1932UbIwerksSoundCartoon.mp4
Flip the Frog & Iwerks | ComiColor: Jack and the Beanstalk | 1933 | JackAndTheBeanstalk1933 | Jack and the Beanstalk (1933).mp4
Flip the Frog & Iwerks | Flip the Frog: Soda Squirt | 1933 | FlipTheFrog-SodaSquirt1933 | FlipTheFrog-SodaSquirt_512kb.mp4
Flip the Frog & Iwerks | Willie Whopper: Stratos Fear | 1933 | StratosFear | StratosFearUbIwerks_512kb.mp4
Flip the Frog & Iwerks | Willie Whopper: The Air Race | 1933 | YheAirRace | AirRaceThe1933WillieWhopperiwerks_512kb.mp4
Flip the Frog & Iwerks | ComiColor: The Headless Horseman | 1934 | ub-iwerks-comicolor-classics-the-complete-collection-1933-36 | Comicolor Cartoons - The Headless Horseman - 1934 (HD).mp4
Flip the Frog & Iwerks | ComiColor: The Little Red Hen | 1934 | ub-iwerks-comicolor-classics-the-complete-collection-1933-36 | Comicolor Cartoons - The Little Red Hen - 1934 (Remastered)  (The first ComiColor cartoon).mp4
Van Beuren | Aesop's Fables: Watered Stock | 1926 | all-van-beuren-cartoons-1921-1936 | Van Beuren Studios Cartoons - 1926x01 - Aesop's Fables Watered Stock.mp4
Van Beuren | Aesop's Fables: A Toytown Tale | 1931 | aesopsFablesAToytownTaleByVanBeurenStudios | VanBeuren_AesopsFable_AToytownTale_512kb.mp4
Van Beuren | Tom and Jerry: Polar Pals | 1931 | all-van-beuren-cartoons-1921-1936 | Van Beuren's Tom & Jerry 02 - Polar Pals.mp4
Van Beuren | Tom and Jerry: Wot a Night | 1931 | TomAndJerryWotANight | WotANight_512kb.mp4
Van Beuren | Tom and Jerry: A Spanish Twist | 1932 | TomAndJerryInASpanishTwist | RareLostCartoonsAndKidsShows-VanBeuren-TomJerry-ASpanishTwistdvdRip1932.mp4
Van Beuren | Tom and Jerry: Pencil Mania | 1932 | PencilMania_482 | VanBeuren-1932-TomJerry-PencilManiadvdRip.mp4
Van Beuren | Tom and Jerry: Rocketeers | 1932 | rocketeers | rocketeers_512kb.mp4
Van Beuren | Cubby Bear: Opening Night | 1933 | van-beurens-cubby-bear-the-complete-collection | Cubby Bear E01 - Opening Night (1933).mp4
Van Beuren | Cubby Bear: The Nut Factory | 1933 | van-beurens-cubby-bear-the-complete-collection | Cubby Bear E08 - The Nut Factory (1933).mp4
Van Beuren | Rainbow Parade: Pastry Town Wedding | 1934 | van-beurens-rainbow-parade-the-complete-collection | Pastry Town Wedding (1934) Van Beuren Studios Rainbow Parade Short Cartoon.mp4
Van Beuren | Rainbow Parade: Molly Moo-Cow and the Indians | 1935 | Molly_Moo-Cow_and_the_Indians_1935 | Molly_Moo-Cow_and_the_Indians_1935_512kb.mp4
Van Beuren | Rainbow Parade: The Sunshine Makers | 1935 | all-van-beuren-cartoons-1921-1936 | The_Sunshine_Makers_1935_512kb.mp4
Private Snafu | Coming!! Snafu | 1943 | private-snafu | Private Snafu S01E01 Coming Snafu.mp4
Private Snafu | Fighting Tools | 1943 | PrivateSnafuCartoons | Private_SNAFU_-_Fighting_Tools_1943.mp4
Private Snafu | Gripes | 1943 | PrivateSnafuCartoons | Private_SnafuGripes.mp4
Private Snafu | Rumors | 1943 | PrivateSnafuCartoons | Private_SNAFU-_Rumors.mp4
Private Snafu | Spies | 1943 | private_snafu_spies | private_snafu_spies_512kb.mp4
Private Snafu | The Goldbrick | 1943 | PrivateSnafuCartoons | Private_Snafu_-_The_Goldbrick.mp4
Private Snafu | The Home Front | 1943 | home_front | home_front_512kb.mp4
Private Snafu | The Infantry Blues | 1943 | Pvt.SNAFU.TheInfantryBlues | Pvt.SNAFU.TheInfantryBlues_512kb.mp4
Private Snafu | A Lecture on Camouflage | 1944 | PrivateSnafuCartoons | Private_Snafu_-_A_Lecture_On_Camouflage_1944.mp4
Private Snafu | Booby Traps | 1944 | booby_traps | booby_traps_512kb.mp4
Private Snafu | Censored | 1944 | PrivateSnafuCartoons | PrivateSnafu-Censored1944WarnerBros.-Youtube.mp4
Private Snafu | Gas | 1944 | PrivateSnafuCartoons | Private_SNAFU_-_Gas_1944.mp4
Private Snafu | Going Home | 1944 | PrivateSnafuCartoons | Private_Snafu_Going_Home.mp4
Private Snafu | Outpost | 1944 | PrivateSnafuCartoons | Private_Snafu_-_Outpost.mp4
Private Snafu | Payday | 1944 | PrivateSnafuCartoons | Private_Snafu_-_Payday.mp4
Private Snafu | Private Snafu vs. Malaria Mike | 1944 | private-snafu | Private Snafu S02E03 Private Snafu vs Malaria Mike_x264.mp4
Private Snafu | Snafuperman | 1944 | PrivateSnafuSnafuperman | Private_Snafu_as_Snafuperman_512kb.mp4
Private Snafu | Target: Snafu | 1944 | private-snafu | Private Snafu S02E11 Target Snafu.mp4
Private Snafu | The Chow Hound | 1944 | PrivateSnafuCartoons | Private_Snafu_-_The_Chow_Hound.mp4
Private Snafu | Three Brothers | 1944 | private-snafu | Private Snafu S01E13 The Three Brothers.mp4
Private Snafu | Hot Spot | 1945 | private-snafu | Private Snafu S03E04 Hot Spot.mp4
Private Snafu | In the Aleutians – Isles of Enchantment | 1945 | private-snafu | Private Snafu S03E01 In The Aleutians.mp4
Private Snafu | It's Murder She Says | 1945 | private-snafu | Private Snafu S03E03 Its Murder She Says.mp4
Private Snafu | No Buddy Atoll | 1945 | private-snafu | Private Snafu S03E06 No Buddy Atoll_x264.mp4
Private Snafu | Operation Snafu | 1945 | private-snafu | Private Snafu S03E05 Operation Snafu.mp4
Private Snafu | Seaman Tarfu in the Navy | 1946 | private-snafu | Private Snafu S04E01 Seaman Tarfu in the Navy.mp4
Specials & holidays | Jack Frost | 1934 | JackFrost_ | JackFrost_512kb.mp4
Specials & holidays | The Lion Tamer (Amos 'n' Andy) | 1934 | TheLionTamer_645 | TheLionTamer-AmosAndAndy_512kb.mp4
Specials & holidays | Christmas Comes But Once a Year | 1936 | ChristmasComesButOnceAYear-1936 | CC-Christmas_Comes_But_Once_A_Year-512K.mp4
Specials & holidays | Gulliver's Travels | 1939 | Gullivers_Travels-1939 | GulliversTravels-1939_512kb.mp4
Specials & holidays | Raggedy Ann and Raggedy Andy | 1941 | RaggedyAnnAndAndy | cartoonFleischer-RaggedyAnnRaggedyAndy1940.mp4
Specials & holidays | Santa's Surprise | 1947 | SantasSuprise | SantasSuprise_512kb.mp4
Specials & holidays | Hector's Hectic Life | 1948 | hectors_hectic_life | hectors_hectic_life_512kb.mp4
Specials & holidays | Rudolph the Red-Nosed Reindeer | 1948 | RudolphTheRed-nosedReindeer1948 | RudolphTheRed-nosedReindeer1948_512kb.mp4
"""
TOON_BADGES = {"Popeye": "POPE", "Looney Tunes": "LOON", "Superman": "SUPE", "Betty Boop": "BOOP",
               "Casper & friends": "CASP", "Mighty Mouse & Terrytoons": "TERR",
               "Woody Woodpecker & Lantz": "WOOD", "Color Classics": "COLR", "Felix & silents": "FELX",
               "Flip the Frog & Iwerks": "FLIP", "Van Beuren": "VANB", "Private Snafu": "SNFU",
               "Specials & holidays": "SPEC"}


# Old films from the Internet Archive, the same way as the cartoons above.
#   folder | title | year | archive.org item | the file in it
FREE_FILMS = """
Comedy & drama | The Front Page | 1931 | TheFrontPage1931AdolpheMenjouPatOBrienLewismiles | TheFrontPage1931AdolpheMenjouPatOBrienLewismiles_512kb.mp4
Comedy & drama | A Farewell to Arms | 1932 | farewell_to_arms | farewell_to_arms_512kb.mp4
Comedy & drama | Rain | 1932 | rain1932 | Rain_512kb.mp4
Comedy & drama | Of Human Bondage | 1934 | humanbondage | HUMANBONDAGE_512kb.mp4
Comedy & drama | My Man Godfrey | 1936 | MyManGodfrey1936 | MyManGodfrey1936_512kb.mp4
Comedy & drama | A Star Is Born | 1937 | AStarIsBorn | AStarIsBorn_512kb.mp4
Comedy & drama | Nothing Sacred | 1937 | NothingSacred | NothingSacred.mp4
Comedy & drama | Algiers | 1938 | Algiers_ | Algiers_512kb.mp4
Comedy & drama | Love Affair | 1939 | LoveAffair | LoveAffair_512kb.mp4
Comedy & drama | Made for Each Other | 1939 | made_for_each_other_film | made_for_each_other_512kb.mp4
Comedy & drama | The Little Princess | 1939 | little_princess | little_princess_512kb.mp4
Comedy & drama | His Girl Friday | 1940 | his_girl_friday | his_girl_friday_512kb.mp4
Comedy & drama | Our Town | 1940 | Our_Town | OurTown_512kb.mp4
Comedy & drama | Second Chorus | 1940 | second_chorus | second_chorus_512kb.mp4
Comedy & drama | Meet John Doe | 1941 | meet_john_doe | meet_john_doe_512kb.mp4
Comedy & drama | Penny Serenade | 1941 | penny_serenade | penny_serenade_512kb.mp4
Comedy & drama | Topper Returns | 1941 | Topper_Returns_41 | Topper_Returns_41_512kb.mp4
Comedy & drama | The Southerner | 1945 | TheSoutherner | TheSoutherner_512kb.mp4
Comedy & drama | Till the Clouds Roll By | 1946 | till_the_clouds_roll_by | till_the_clouds_roll_by_512kb.mp4
Comedy & drama | Life with Father | 1947 | LifeWithFather | LifeWithFather_512kb.mp4
Comedy & drama | Africa Screams | 1949 | AfricaScreams | Africa_Screams_512kb.mp4
Comedy & drama | The Inspector General | 1949 | the_inspector_general | the_inspector_general_512kb.mp4
Comedy & drama | Father's Little Dividend | 1951 | fatherslittledividend | FathersLittleDividend_512kb.mp4
Comedy & drama | Royal Wedding | 1951 | royal_wedding | royal_wedding_512kb.mp4
Comedy & drama | Jack and the Beanstalk | 1952 | cco_jackandthebeanstalk | ccoPublicDomainJack_and_the_Beanstalk_512kb.mp4
Comedy & drama | Road to Bali | 1952 | TheRoadToBali | ClassicCinemaOnline-road_to_bali_256kb.mp4
Comedy & drama | The Last Time I Saw Paris | 1954 | last_time_i_saw_paris | last_time_i_saw_paris_512kb.mp4
Comedy & drama | The Man with the Golden Arm | 1955 | the-man-with-the-golden-arm-1955_202405 | The Man With The Golden Arm 1955.mp4
Comedy & drama | Charade | 1963 | ecatma-Old_Time_Movie_Show_-_Charade_1963 | Old_Time_Movie_Show_-_Charade_1963.mp4
Film noir & crime | Sherlock Holmes and the Secret Weapon | 1942 | secret_weapon | sherlock_holmes_and_the_secret_weapon_512kb.mp4
Film noir & crime | Bluebeard | 1944 | Bluebeard | Bluebeard_512kb.mp4
Film noir & crime | Detour | 1945 | Detour | Detour_512kb.mp4
Film noir & crime | Scarlet Street | 1945 | ScarletStreet | Scarlet_Street_512kb.mp4
Film noir & crime | Strange Illusion | 1945 | Strange_Illusion | Strange_Illusion_512kb.mp4
Film noir & crime | The Great Flamarion | 1945 | Great_Flamarion_1945 | Great_Flamarion_512kb.mp4
Film noir & crime | The Woman in Green | 1945 | TWIG1945 | The_Woman_in_Green_512kb.mp4
Film noir & crime | Dressed to Kill | 1946 | dressed_to_kill | dressed_to_kill_512kb.mp4
Film noir & crime | Shock | 1946 | shock | Shock_512kb.mp4
Film noir & crime | Terror by Night | 1946 | Terror_By_Night | Terror_By_Night_512kb.mp4
Film noir & crime | The Chase | 1946 | thechase1946_202002 | The Chase (1946, USA) Featuring Peter Lorre, Robert Cummings - Film Noir Full Movie.mp4
Film noir & crime | The Stranger | 1946 | TheStranger_0 | The_Stranger_512kb.mp4
Film noir & crime | Fear in the Night | 1947 | Fear_in_the_Night | Fear_in_the_Night_512kb.mp4
Film noir & crime | Railroaded! | 1947 | railroaded1947_202003 | Railroaded! (1947, USA) Directed by Anthony Mann Featuring John Ireland - Film Noir Full Movie.mp4
Film noir & crime | The Red House | 1947 | TheRedHouse | The_Red_House_512kb.mp4
Film noir & crime | Blonde Ice | 1948 | BlondeIce1948 | BlondeIce1948_512kb.mp4
Film noir & crime | D.O.A. | 1949 | D.o.a.VideoQualityUpgrade | D.o.a.VideoQualityUpgrade.mp4
Film noir & crime | Impact | 1949 | impact | impact_512kb.mp4
Film noir & crime | Port of New York | 1949 | Port_of_New_York | Port_of_New_York_512kb.mp4
Film noir & crime | Too Late for Tears | 1949 | 7.3-too-late-for-tears-1949 | 7.3 Too Late for Tears (1949).ia.mp4
Film noir & crime | Trapped | 1949 | Trapped_ | Trapped_512kb.mp4
Film noir & crime | Quicksand | 1950 | Quicksand_clear | Quicksand.mp4
Film noir & crime | The Man Who Cheated Himself | 1950 | TheManWhoCheatedHimself1950 | TheManWhoCheatedHimself1950.mp4
Film noir & crime | The Second Woman | 1950 | The_Second_Woman_ | The_Second_Woman__512kb.mp4
Film noir & crime | Woman on the Run | 1950 | Woman_on_the_Run | Woman_on_the_Run_512kb.mp4
Film noir & crime | Kansas City Confidential | 1952 | KansasCityConfidential720p | KansasCityConfidential1952-720p_512kb.mp4
Film noir & crime | The Bigamist | 1953 | the_bigamist | the_bigamist_512kb.mp4
Film noir & crime | The Hitch-Hiker | 1953 | Hitch_Hiker | Hitch-Hiker_512kb.mp4
Film noir & crime | Suddenly | 1954 | suddenly | suddenly_512kb.mp4
Film noir & crime | The Big Combo | 1955 | TheBigComboCornellWilde1955BOO | TheBigComboCornellWilde1955BOO_512kb.mp4
Horror & sci-fi | White Zombie | 1932 | white_zombie | white_zombie_512kb.mp4
Horror & sci-fi | The Devil Bat | 1940 | Devil_Bat_movie | Devil_Bat_512kb.mp4
Horror & sci-fi | Dead Men Walk | 1943 | DeadMenWalk | DeadMenWalk.mp4
Horror & sci-fi | The Ape Man | 1943 | TheApeMan | TheApeMan_512kb.mp4
Horror & sci-fi | Voodoo Man | 1944 | VoodooManVideoAudioUpgrade | VoodooManVideoAudioUpgrade.mp4
Horror & sci-fi | Scared to Death | 1947 | SCAREDTODEATHVideoQualityUpgrade | SCARED TO DEATH video quality upgrade.mp4
Horror & sci-fi | Phantom from Space | 1953 | PHANTOMFROMSPACEVideoQualityUpgrade | PHANTOM FROM SPACE video quality upgrade.mp4
Horror & sci-fi | Robot Monster | 1953 | robot-monster-1953 | Robot Monster (1953).mp4
Horror & sci-fi | Killers from Space | 1954 | Killers_from_space | Killers_from_space_512kb.mp4
Horror & sci-fi | Indestructible Man | 1956 | indestructible_man | indestructible_man_512kb.mp4
Horror & sci-fi | Plan 9 from Outer Space | 1957 | plan-9-from-outer-space | plan-9-from-outer-space.mp4
Horror & sci-fi | The Screaming Skull | 1958 | TheScreamingSkullHD1958 | TheScreamingSkullHD1958.mp4
Horror & sci-fi | A Bucket of Blood | 1959 | ABucketofBlood | Bucket_1959_512kb.mp4
Horror & sci-fi | Attack of the Giant Leeches | 1959 | AttackOfTheGiantLeeches | AttackOfTheGiantLeeches_512kb.mp4
Horror & sci-fi | Beast from Haunted Cave | 1959 | BeastFromHauntedCave1959 | BeastFromHauntedCave1959_512kb.mp4
Horror & sci-fi | House on Haunted Hill | 1959 | House_On_Haunted_Hill.avi | The_House_on_Haunted_Hill_512kb.mp4
Horror & sci-fi | Teenagers from Outer Space | 1959 | TeenagersFromOuterSpace | TeenagersFromOuterSpace_512kb.mp4
Horror & sci-fi | The Bat | 1959 | The_Bat.mpeg | The_Bat_512kb.mp4
Horror & sci-fi | The Giant Gila Monster | 1959 | TheGiantGilaMonsterWidescreenQualityUpgrade | THE GIANT GILA MONSTER.mp4
Horror & sci-fi | The Killer Shrews | 1959 | TheKillerShrews | The_Killer_Shrews.mp4
Horror & sci-fi | The Wasp Woman | 1959 | The_Wasp_Women | The_Wasp_Women_512kb.mp4
Horror & sci-fi | The Little Shop of Horrors | 1960 | The_Little_Shop_of_Horrors_60 | The_Little_Shop_of_Horrors_60.mp4
Horror & sci-fi | Night Tide | 1961 | NightTide1961 | NightTide1961_512kb.mp4
Horror & sci-fi | Carnival of Souls | 1962 | CarnivalofSouls | CarnivalOfSouls_512kb.mp4
Horror & sci-fi | The Brain That Wouldn't Die | 1962 | brain_that_wouldnt_die | brain_that_wouldnt_die_512kb.mp4
Horror & sci-fi | Dementia 13 | 1963 | dementia-13-1963_202312 | Dementia 13 (1963).mp4
Horror & sci-fi | The Terror | 1963 | TheTerrorwidescreen | RogerCormansTheTerror1963FullMovie-WidescreenVersion_512kb.mp4
Horror & sci-fi | The Last Man on Earth | 1964 | lastmanonearth-1964 | lastmanonearth-1964.mp4
Horror & sci-fi | Night of the Living Dead | 1968 | NightOfTheLivingDead-MPEG | NightOfTheLivingDead_512kb.mp4
Westerns & adventure | The Mark of Zorro | 1920 | the-mark-of-zorro-1920 | The Mark Of Zorro (1920).mp4
Westerns & adventure | Robin Hood | 1922 | FairbanksRobinHood1922 | FairbanksRobinHood1922/FairbanksRobinHood1922_512kb.mp4
Westerns & adventure | The Thief of Bagdad | 1924 | TheThiefOfBagdad1924 | TOB1924-512.mp4
Westerns & adventure | The Black Pirate | 1926 | the-black-pirate-1926 | The Black Pirate 1926.ia.mp4
Westerns & adventure | Riders of Destiny | 1933 | RidersofDestiny_ | RidersofDestiny_512kb.mp4
Westerns & adventure | Sagebrush Trail | 1933 | SagebrushTrail | SagebrushTrail_512kb.mp4
Westerns & adventure | 'Neath the Arizona Skies | 1934 | NeaththeArizonaSkys | NeaththeArizonaSkys_512kb.mp4
Westerns & adventure | Blue Steel | 1934 | BlueSteel | BlueSteel_512kb.mp4
Westerns & adventure | Randy Rides Alone | 1934 | RandyRidesAlone | RandyRideAlone_512kb.mp4
Westerns & adventure | The Lawless Frontier | 1934 | TheLawlessFontier | TheLawlessFontier_512kb.mp4
Westerns & adventure | The Lucky Texan | 1934 | TheLuckyTexan | TheLuckyTexan_512kb.mp4
Westerns & adventure | The Man from Utah | 1934 | TheManFromUtah | TheManFromUtah_512kb.mp4
Westerns & adventure | The Star Packer | 1934 | The_Star_Packer | The_Star_Packer_512kb.mp4
Westerns & adventure | The Trail Beyond | 1934 | TheTrailBeyond | TheTrailBeyond_512kb.mp4
Westerns & adventure | West of the Divide | 1934 | west_of_the_divide | west_of_the_divide_512kb.mp4
Westerns & adventure | Paradise Canyon | 1935 | ParadiseCanyon | ParadiseCanyon_512kb.mp4
Westerns & adventure | Rainbow Valley | 1935 | RainbowValley | RainbowValley_512kb.mp4
Westerns & adventure | Texas Terror | 1935 | texas_terror_1935 | texas_terror_1935_512kb.mp4
Westerns & adventure | The Dawn Rider | 1935 | TheDawnRider | TheDawnRider_512kb.mp4
Westerns & adventure | The Desert Trail | 1935 | TheDesertTrail | TheDesertTrail_512kb.mp4
Westerns & adventure | The New Adventures of Tarzan | 1935 | new_adventures_of_tarzan | new_adventures_of_tarzan_512kb.mp4
Westerns & adventure | Tarzan and the Green Goddess | 1938 | tarzan_and_the_green_goddess | tarzan_and_the_green_goddess_512kb.mp4
Westerns & adventure | Santa Fe Trail | 1940 | SantaFeTrail1940 | SantaFeTrail1940_512kb.mp4
Westerns & adventure | Jungle Book | 1942 | JungleBook | Jungle_Book_512kb.mp4
Westerns & adventure | Captain Kidd | 1945 | CaptainKidd_ | CaptainKidd_512kb.mp4
Westerns & adventure | Abilene Town | 1946 | AbileneTown | AbileneTown_512kb.mp4
Westerns & adventure | Angel and the Badman | 1947 | angel_and_the_badman | angel_and_the_badman_512kb.mp4
Westerns & adventure | Kansas Pacific | 1953 | KansasPacific | KansasPacific_512kb.mp4
Westerns & adventure | McLintock! | 1963 | Mclintock.avi | Mclintock_512kb.mp4
Silent classics | A Trip to the Moon | 1902 | 1902-a-trip-to-the-moon | 1902   A Trip To The Moon.mp4
Silent classics | The Great Train Robbery | 1903 | silent-the-great-train-robbery | The Great Train Robbery.mp4
Silent classics | The Rink | 1916 | silent-the-rink | The Rink.mp4
Silent classics | Easy Street | 1917 | silent-easy-street | Easy Street.mp4
Silent classics | The Adventurer | 1917 | silent-the-adventurer | The Adventurer.mp4
Silent classics | The Cure | 1917 | silent-the-cure | The Cure.mp4
Silent classics | The Immigrant | 1917 | silent-the-immigrant | The Immigrant.mp4
Silent classics | Dr. Jekyll and Mr. Hyde | 1920 | DrJekyllandMrHyde | DrJekyllandMrHyde_512kb.mp4
Silent classics | The Cabinet of Dr. Caligari | 1920 | thecabinetofdrcaligari | KabinettDesDoktorCaligariDas_512kb.mp4
Silent classics | Häxan | 1922 | Haxan1922 | Haxan (1922).mp4
Silent classics | Nosferatu | 1922 | nosferatu-1922-silent-movie | Nosferatu -1922- -Silent Movie-.mp4
Silent classics | Our Hospitality | 1923 | OurHospitality_29 | OurHospitality_512kb.mp4
Silent classics | Safety Last! | 1923 | silent-safety-last | Safety Last!.mp4
Silent classics | The Hunchback of Notre Dame | 1923 | The_Hunchback_of_Notre_Dame | The_Hunchback_of_Notre_Dame_512kb.mp4
Silent classics | Sherlock Jr. | 1924 | silent-sherlock-jr- | Sherlock Jr..mp4
Silent classics | The Navigator | 1924 | the-navigator-1924. | The Navigator 1924. .mp4
Silent classics | Battleship Potemkin | 1925 | BattleshipPotemkin | Battleship_Potemkin_512kb.mp4
Silent classics | Seven Chances | 1925 | silent-seven-chances | Seven Chances.mp4
Silent classics | The Freshman | 1925 | silent-the-freshman | The Freshman.mp4
Silent classics | The Lost World | 1925 | TheLostWorld1925 | TheLostWorld1925_512.mp4
Silent classics | The Phantom of the Opera | 1925 | ThePhantomOfTheOpera_364 | ThePhantomOfTheOperaPresentedByMoviePowder_512kb.mp4
Silent classics | The General | 1926 | TheGeneral | The_General_512kb.mp4
Silent classics | College | 1927 | college | College_512kb.mp4
Silent classics | It | 1927 | it_20240118 | it.mp4
Silent classics | Metropolis | 1927 | metropolis_202109 | Metropolis.ia.mp4
Silent classics | Sunrise: A Song of Two Humans | 1927 | sunrise-1927_202301 | Sunrise.ia.mp4
Silent classics | Wings | 1927 | wings_1927 | Wings (1927).mp4
Silent classics | Steamboat Bill, Jr. | 1928 | steamboat-bill-jr_1928 | steamboat-bill-jr_1928.ia.mp4
Silent classics | The Passion of Joan of Arc | 1928 | MartyreDeJeanneDarc | Jeanne Darc.mp4
"""
FILM_BADGES = {"Comedy & drama": "COMD", "Film noir & crime": "NOIR", "Horror & sci-fi": "HORR",
               "Westerns & adventure": "WEST", "Silent classics": "SILN"}

def archive_shelves(text):
    """folder -> [(title, year, item, file)], in the order they're listed."""
    out = {}
    for line in text.strip().splitlines():
        parts = line.split(" | ")
        if len(parts) == 5 and not line.startswith("#"):
            folder, title, year, ident, name = (x.strip() for x in parts)
            out.setdefault(folder, []).append((title, year, ident, name))
    return out


CLASSIC = archive_shelves(CLASSIC_TOONS)
FILMS = archive_shelves(FREE_FILMS)
SHELVES = {"toons": (CLASSIC, TOON_BADGES, "cartoons"), "movies": (FILMS, FILM_BADGES, "films")}
PLEX_FOLDERS = {"toons": [("Anime", "ANIM", "anime"), ("Cartoon channels", "live", "toons")],
                "movies": [("Movie channels", "live", "movies")]}
IA_URLS = {}       # cartoon or film -> the lightest copy of it, once looked up


def ia_row(folder, title, year, ident, name):
    src = f"ia:{ident}/{name}"
    return dict(item(src, title, "video", src, sub=year), folder=folder)


def is_hls(url):
    """A live stream that lists its versions (an .m3u8), for hls_pick to choose from."""
    try:
        return urllib.parse.urlsplit(url).path.lower().endswith(".m3u8")
    except ValueError:                   # not a link at all (a typo in streams.txt)
        return False


# FFmpeg (mplayer plays streams through its libavformat) turns down a stream whose pieces' links don't end in a kind
# of file it knows (".../640x360_800000?u=...": some free channels make theirs up as they're asked for), since its
# 2025 fixes (5.1.7 on). It can be told not to mind. An older one doesn't know how to be told, and doesn't mind
# anyway; and mplayer plays nothing at all given a word its FFmpeg doesn't know, so it's only said to one that knows.
HLS_LENIENT = ["-lavfdopts", "o=extension_picky=0"]
HLS_TURNED_DOWN = ("allowed_segment_extensions", "mismatches allowed extensions")   # (what FFmpeg says, doing it)
LAVF_LIBS = ("/usr/lib/*/libavformat.so.*", "/usr/lib/libavformat.so.*", "/usr/local/lib/*/libavformat.so.*",
             "/usr/local/lib/libavformat.so.*")
_lavf_knows = {}                         # word -> whether the FFmpeg here knows it (looked at once)


def lavf_knows(word):
    """Whether the FFmpeg mplayer plays through knows this word: it's in each libavformat here (mplayer's is one)."""
    if word not in _lavf_knows:
        libs = {os.path.realpath(p) for pattern in LAVF_LIBS for p in glob.glob(pattern)}

        def has(path):
            try:
                with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
                    return m.find(word.encode() + b"\0") >= 0
            except (OSError, ValueError):
                return False
        _lavf_knows[word] = bool(libs) and all(has(p) for p in libs)
    return _lavf_knows[word]


def lavf_knows_now(word):
    """The FFmpeg here has been seen to know this word (it said it)."""
    _lavf_knows[word] = True


def hls_lenient():
    """mplayer's words for an HLS stream, that FFmpeg's not to mind what its pieces' links end in ([] if its FFmpeg
    doesn't know them)."""
    return list(HLS_LENIENT) if lavf_knows("extension_picky") else []


def hls_turned_down(said):
    """Whether what the player said (its last lines) is FFmpeg turning a stream down for its pieces' links: then its
    FFmpeg knows how to be told not to mind, too."""
    return any(w in line for line in said for w in HLS_TURNED_DOWN)


def hls_pick(url, timeout=8):
    """A live stream's version closest to the screen's size (the big ones stutter on the Pi),
    or the stream as it is when it has one version or keeps its sound apart."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final, text = r.geturl(), r.read(200_000).decode("utf-8", "ignore")
    except Exception:
        return url
    if re.search(r"#EXT-X-MEDIA:[^\n]*TYPE=AUDIO[^\n]*URI=", text):
        return url                      # one version alone would have no sound
    variants, info = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            res = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            info = (int(res.group(2)) if res else 0, int(bw.group(1)) if bw else 0)
        elif line and not line.startswith("#") and info:
            variants.append((info, line))
            info = None
    if len(variants) < 2:
        return url
    lines = video_target()[2]
    small = [v for v in variants if 0 < v[0][0] <= lines]
    pick = max(small, key=lambda v: v[0]) if small else min(variants, key=lambda v: v[0])
    try:
        return urllib.parse.urljoin(final, pick[1])
    except ValueError:                   # a version listed with a broken link
        return url


def ia_best(ident, name, timeout=8):
    """Where to stream a cartoon from: the lightest copy of it in its archive.org item (the
    320x240 one plays easily on the Pi and is fine on this screen), or the file listed in
    CLASSIC_TOONS if the Archive doesn't say."""
    base = "https://archive.org/download/" + urllib.parse.quote(ident) + "/"
    known = base + urllib.parse.quote(name)
    if known in IA_URLS:
        return IA_URLS[known]
    try:
        files = fetch_json("https://archive.org/metadata/" + urllib.parse.quote(ident), timeout).get("files") or []
    except Exception:
        return known
    vids = [f for f in files if f.get("name", "").lower().endswith(tuple(VIDEO_EXTS) + (".ogv",))]

    def source(f):                       # the file a copy was made from
        return f.get("original") if f.get("source") == "derivative" and f.get("original") else f.get("name")
    me = next((f for f in vids if f.get("name") == name), None)
    if me is not None:
        key = source(me)
    elif len({source(f) for f in vids}) == 1:     # renamed, but it's the item's only video
        key = source(vids[0])
    else:
        return known
    copies = [f for f in vids if source(f) == key]
    mp4 = [f for f in copies if f["name"].lower().endswith(".mp4")] or copies
    best = min(mp4, key=lambda f: int(f.get("size") or 1 << 40))
    IA_URLS[known] = base + urllib.parse.quote(best["name"])
    return IA_URLS[known]
