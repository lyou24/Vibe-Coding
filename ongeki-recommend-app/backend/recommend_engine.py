import json
import os
import math
from glob import glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MASTER_FILE = os.path.join(DATA_DIR, "music_master.json")

def load_music_master():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_user_data(user_id):
    path = os.path.join(DATA_DIR, f"user_{user_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def calc_ts_rating(score, constant, lamp="", fb=False):
    if score >= 1010000: base = constant + 2.000 + ((score - 1010000) // 10) * 0.001
    elif score >= 1007500: base = constant + 1.750 + ((score - 1007500) // 10) * 0.001
    elif score >= 1000000: base = constant + 1.250 + ((score - 1000000) // 15) * 0.001
    elif score >= 990000: base = constant + 0.750 + ((score - 990000) // 20) * 0.001
    elif score >= 970000: base = constant + 0.000 + ((score - 970000) // 26.666666666666668) * 0.001
    elif score >= 900000: base = constant - 4.000 + ((score - 900000) // 17.5) * 0.001
    elif score >= 800000: base = constant - 6.000 + ((score - 800000) // 50) * 0.001
    else: base = 0.0

    mark_bonus = 0.0
    if score >= 1010000: mark_bonus += 0.3
    elif score >= 1000000: mark_bonus += 0.2
    elif score >= 990000: mark_bonus += 0.1

    is_ab = "AB" in lamp
    is_fb = "FB" in lamp or fb
    is_fc = "FC" in lamp or is_fb

    if score >= 1010000 or "AB+" in lamp: mark_bonus += 0.35
    elif is_ab: mark_bonus += 0.3
    elif is_fc: mark_bonus += 0.1
        
    return min(base + mark_bonus, constant + 2.7)

def reverse_calc_ts(expected_rate, constant):
    def _reverse_base(diff):
        if diff >= 2.3: return 1010000 + math.ceil((diff - 2.3) * 10000)
        elif diff > 2.199: return 1010000
        elif diff >= 1.95: return 1007500 + math.ceil((diff - 1.95) * 10000)
        elif diff >= 1.45: return 1000000 + math.ceil((diff - 1.45) * 15000)
        elif diff > 1.349: return 1000000
        elif diff >= 0.85: return 990000 + math.ceil((diff - 0.85) * 20000)
        elif diff > 0.749: return 990000
        elif diff >= 0.0: return 970000 + math.ceil(diff * 26666.667)
        else: return 970000

    score_if_ab = _reverse_base(expected_rate - constant - 0.35)
    if score_if_ab >= 1008000:
        return score_if_ab
        
    return _reverse_base(expected_rate - constant - 0.15)

class RecommendEngine:
    _active_keys_cache = None

    @classmethod
    def get_active_keys(cls):
        if cls._active_keys_cache is None:
            active_keys = set()
            user_files = glob(os.path.join(DATA_DIR, "user_*.json"))
            for uf in user_files:
                try:
                    with open(uf, "r", encoding="utf-8") as f:
                        udata = json.load(f)
                    active_keys.update(udata.get("scores", {}).keys())
                except Exception:
                    pass
            cls._active_keys_cache = active_keys
        return cls._active_keys_cache

    def __init__(self, target_user_id="10605"):
        self.target_user_id = target_user_id
        self.music_master = load_music_master()
        self.music_dict = {f"{m['id']}_{m['difficulty']}": m for m in self.music_master}
        self.load_all_data()
        
    def get_profile_rates(self, user_data):
        prof = {}
        for key, sc in user_data.get("scores", {}).items():
            if key not in self.music_dict: continue
            const = self.music_dict[key]["constant"]
            prof[key] = calc_ts_rating(sc["ts"], const, sc.get("lamp", ""), sc.get("fb", False))
        return prof

    def load_all_data(self):
        self.target_data = load_user_data(self.target_user_id)
        if not self.target_data:
            print("Target user data not found.")
            return

        t_rp = self.target_data.get("rating_profile", {})
        t_b = t_rp.get("borders", {})
        t_best_avg = t_b.get("best_avg", 0)
        t_new_avg = t_b.get("new_avg", 0)
        t_ps_avg = t_b.get("ps_avg", 0)
        
        if t_best_avg > 0 or t_new_avg > 0:
            self.target_rating = (t_best_avg * 50 + t_new_avg * 10 + t_ps_avg * 50) / 50
        else:
            t_prof = self.get_profile_rates(self.target_data)
            t_rates = sorted(t_prof.values(), reverse=True)
            self.target_rating = sum(t_rates[:50]) / 50 if t_rates else 0

        print(f"Target Rating: {self.target_rating:.2f}")

        self.users_data_025 = {}
        self.users_data_050 = {}
        self.users_data_p050 = {}

        for filepath in glob(os.path.join(DATA_DIR, "user_*.json")):
            filename = os.path.basename(filepath)
            if not filename.startswith("user_") or filename == f"user_{self.target_user_id}.json":
                continue
            
            uid = filename[5:-5]
            data = load_user_data(uid)
            if not data: continue
            
            if "scores" not in data: data = {"scores": data, "rating_profile": {}}
            
            if "rating_profile" in data and "borders" in data["rating_profile"]:
                b = data["rating_profile"]["borders"]
                b_best = b.get("best_avg", 0)
                b_new = b.get("new_avg", 0)
                b_ps = b.get("ps_avg", 0)
                if b_best > 0 or b_new > 0:
                    pseudo_rating = (b_best * 50 + b_new * 10 + b_ps * 50) / 50
                else:
                    prof_tmp = self.get_profile_rates(data)
                    rates_tmp = sorted(prof_tmp.values(), reverse=True)
                    pseudo_rating = sum(rates_tmp[:50]) / 50 if rates_tmp else 0
            else:
                prof_tmp = self.get_profile_rates(data)
                rates_tmp = sorted(prof_tmp.values(), reverse=True)
                pseudo_rating = sum(rates_tmp[:50]) / 50 if rates_tmp else 0

            diff = abs(pseudo_rating - self.target_rating)
            if diff <= 0.25: self.users_data_025[uid] = data
            if diff <= 0.50: self.users_data_050[uid] = data
            
            diff_raw = pseudo_rating - self.target_rating
            if 0.0 <= diff_raw <= 0.50: self.users_data_p050[uid] = data

    def analyze_group(self, group_users, matrix_lookup=None):
        t_prof = self.get_profile_rates(self.target_data)
        t_rp = self.target_data.get("rating_profile", {})
        t_b = t_rp.get("borders", {})
        
        border_new = t_b.get("new", 0)
        border_best = t_b.get("best", 0)
        border_ps = t_b.get("ps", 0)
        border_ps_avg = t_b.get("ps_avg", 0)
        
        t_new_keys = set([k["key"] for k in t_rp.get("new_songs", [])])
        t_best_keys = set([k["key"] for k in t_rp.get("best_songs", [])])
        t_ps_keys = set([k["key"] for k in t_rp.get("ps_songs", [])])
        t_all_keys = t_new_keys | t_best_keys | t_ps_keys

        stats_new = {}
        stats_best = {}
        stats_ps = {}
        total_u = len(group_users)
        if total_u == 0: total_u = 1

        for uid, data in group_users.items():
            prof = self.get_profile_rates(data)
            rp = data.get("rating_profile", {})
            
            for k in rp.get("new_songs", []):
                key = k["key"]
                rate = prof.get(key, 0)
                if rate < border_new: continue
                if key not in stats_new: stats_new[key] = {"count": 0, "rates": []}
                stats_new[key]["count"] += 1
                stats_new[key]["rates"].append(rate)
                
            for k in rp.get("best_songs", []):
                key = k["key"]
                rate = prof.get(key, 0)
                if rate < border_best: continue
                if key not in stats_best: stats_best[key] = {"count": 0, "rates": []}
                stats_best[key]["count"] += 1
                stats_best[key]["rates"].append(rate)
                
            for k in rp.get("ps_songs", []):
                key = k["key"]
                stars = k.get("stars", 0)
                const = self.music_dict.get(key, {}).get("constant", 0)
                other_ps_rate = (const ** 2) * stars / 1000
                if other_ps_rate < border_ps: continue
                if key not in stats_ps: stats_ps[key] = {"count": 0, "stars": []}
                stats_ps[key]["count"] += 1
                stats_ps[key]["stars"].append(stars)

        t_ps_stars = {k["key"]: k.get("stars", 0) for k in t_rp.get("ps_songs", [])}

        def build_rec(stats_dict, exclude_keys, border, is_ps=False):
            res = []
            for key, st in stats_dict.items():
                adopt = st["count"] / total_u
                if adopt >= 0.1 and key not in exclude_keys:
                    music = self.music_dict[key]
                    const = music["constant"]
                    my_rate = t_prof.get(key, 0)
                    my_ts = self.target_data.get("scores", {}).get(key, {}).get("ts", 0)
                    my_lamp = self.target_data.get("scores", {}).get(key, {}).get("lamp", "-")
                    
                    if is_ps:
                        target_star_raw = sorted(st["stars"])[math.floor(len(st["stars"]) * 0.25)]
                        target_star = round(target_star_raw)
                        expected_rate = (const ** 2) * target_star / 1000
                        my_star = t_ps_stars.get(key, 0)
                        
                        if expected_rate > border_ps_avg and target_star > my_star:
                            res.append({
                                "key": key,
                                "title": music["title"],
                                "version": music.get("version", "Unknown"),
                                "adopt_rate": adopt,
                                "expected_rate": expected_rate,
                                "target_star": target_star,
                                "my_star": my_star,
                                "my_lamp": my_lamp,
                                "constant": const
                            })
                    else:
                        val = sorted(st["rates"])[math.floor(len(st["rates"]) * 0.25)]
                        if val > border and val > my_rate:
                            res.append({
                                "key": key,
                                "title": music["title"],
                                "version": music.get("version", "Unknown"),
                                "adopt_rate": adopt,
                                "expected_rate": val,
                                "my_rate": my_rate,
                                "my_ts": my_ts,
                                "my_lamp": my_lamp,
                                "target_score": reverse_calc_ts(val, const),
                                "constant": const
                            })
            res.sort(key=lambda x: x["adopt_rate"] * x["expected_rate"], reverse=True)
            return res

        rec_new = build_rec(stats_new, t_new_keys, border_new)
        rec_best = build_rec(stats_best, t_best_keys, border_best)
        rec_ps = build_rec(stats_ps, t_ps_keys, border_ps, is_ps=True)
        
        weapons_stats = {}
        higher_users_count = 0
        for uid, data in group_users.items():
            b = data.get("rating_profile", {}).get("borders", {})
            b_best = b.get("best_avg", 0)
            b_new = b.get("new_avg", 0)
            b_ps = b.get("ps_avg", 0)
            if b_best > 0 or b_new > 0:
                pseudo_rating = (b_best * 50 + b_new * 10 + b_ps * 50) / 50
            else:
                prof_tmp = self.get_profile_rates(data)
                rates_tmp = sorted(prof_tmp.values(), reverse=True)
                pseudo_rating = sum(rates_tmp[:50]) / 50 if rates_tmp else 0
                
            if self.target_rating <= pseudo_rating <= self.target_rating + 0.5:
                higher_users_count += 1
                prof_u = self.get_profile_rates(data)
                for key in (t_best_keys | t_new_keys):
                    if key not in weapons_stats: weapons_stats[key] = {"count": 0, "rates": []}
                    rate = prof_u.get(key, 0)
                    border = border_new if key in t_new_keys else border_best
                    if rate >= border:
                        weapons_stats[key]["count"] += 1
                        weapons_stats[key]["rates"].append(rate)

        if higher_users_count == 0: higher_users_count = 1

        weapons = []
        for key in (t_best_keys | t_new_keys):
            st = weapons_stats.get(key)
            if not st or st["count"] == 0: continue
            
            adopt = st["count"] / higher_users_count
            if adopt <= 0.30:  # 採用率を30%以下に緩和
                my_rate = t_prof.get(key, 0)
                # 他者のスコア(val)との比較は撤廃
                if my_rate >= border_best + 0.05:  # ボーダー要件を+0.05に緩和
                    music = self.music_dict[key]
                    weapons.append({
                        "key": key,
                        "title": music["title"],
                        "version": music.get("version", "Unknown"),
                        "adopt_rate": adopt,
                        "my_rate": my_rate,
                        "my_ts": self.target_data.get("scores", {}).get(key, {}).get("ts", 0),
                        "my_lamp": self.target_data.get("scores", {}).get(key, {}).get("lamp", "-"),
                        "constant": music["constant"]
                    })
        weapons.sort(key=lambda x: x["my_rate"], reverse=True)

        user_sims = []
        def get_weight(key):
            const = self.music_dict.get(key, {}).get("constant", 13.0)
            return 1.0 + max(0, const - 13.0) * 0.2

        for uid, data in group_users.items():
            rp = data.get("rating_profile", {})
            u_keys = set([k["key"] for k in rp.get("best_songs", [])])
            inter_keys = t_best_keys & u_keys
            union_keys = t_best_keys | u_keys
            inter_weight = sum(get_weight(k) for k in inter_keys)
            union_weight = sum(get_weight(k) for k in union_keys)
            jaccard = inter_weight / union_weight if union_weight > 0 else 0
            user_sims.append({"uid": uid, "jaccard": jaccard, "keys": u_keys, "prof": self.get_profile_rates(data)})
            
        user_sims = [u for u in user_sims if u["jaccard"] >= 0.15]
        user_sims.sort(key=lambda x: x["jaccard"], reverse=True)
        dynamic_n = max(10, min(50, int(total_u * 0.05)))
        top_sims = user_sims[:dynamic_n]
        
        sim_stats = {}
        for u in top_sims:
            for k in u["keys"]:
                rate = u["prof"].get(k, 0)
                if rate < border_best: continue
                if k not in sim_stats: sim_stats[k] = {"count": 0, "rates": []}
                sim_stats[k]["count"] += 1
                sim_stats[k]["rates"].append(rate)
                
        rec_sim = []
        for key, st in sim_stats.items():
            adopt = st["count"] / len(top_sims)
            if adopt >= 0.3 and key not in t_all_keys:
                exp = sorted(st["rates"])[math.floor(len(st["rates"]) * 0.25)]
                if exp > border_best:
                    m = self.music_dict[key]
                    rec_sim.append({
                        "key": key,
                        "title": m["title"],
                        "version": m.get("version", "Unknown"),
                        "adopt_rate": adopt,
                        "expected_rate": exp,
                        "my_rate": t_prof.get(key, 0),
                        "my_ts": self.target_data.get("scores", {}).get(key, {}).get("ts", 0),
                        "my_lamp": self.target_data.get("scores", {}).get(key, {}).get("lamp", "-"),
                        "target_score": reverse_calc_ts(exp, m["constant"]),
                        "constant": m["constant"]
                    })
        rec_sim.sort(key=lambda x: x["adopt_rate"] * x["expected_rate"], reverse=True)

        # Rank & Lamp Recommend (SS->SSS, SSS->SSS+, FC, AB) for constant >= 13.0
        rank_stats = {}
        for uid, data in group_users.items():
            u_scores = data.get("scores", {})
            for key, sc in u_scores.items():
                m = self.music_dict.get(key)
                if not m or m.get("constant", 0) < 13.0:
                    continue
                ts = sc.get("ts", 0)
                if ts <= 0:
                    continue
                lamp = sc.get("lamp", "")
                if key not in rank_stats:
                    rank_stats[key] = {"sss_count": 0, "sssp_count": 0, "fc_count": 0, "ab_count": 0}
                if ts >= 1000000:
                    rank_stats[key]["sss_count"] += 1
                if ts >= 1007500:
                    rank_stats[key]["sssp_count"] += 1
                if "FC" in lamp or "AB" in lamp:
                    rank_stats[key]["fc_count"] += 1
                if "AB" in lamp:
                    rank_stats[key]["ab_count"] += 1

        rec_rank_sss = []
        rec_rank_sssp = []
        rec_lamp_fc = []
        rec_lamp_ab = []

        t_scores = self.target_data.get("scores", {})

        for key, music in self.music_dict.items():
            if music.get("constant", 0) < 13.0:
                continue

            st = rank_stats.get(key, {"sss_count": 0, "sssp_count": 0, "fc_count": 0, "ab_count": 0})
            sss_rate = st["sss_count"] / total_u
            sssp_rate = st["sssp_count"] / total_u
            fc_rate = st["fc_count"] / total_u
            ab_rate = st["ab_count"] / total_u

            sc = t_scores.get(key, {})
            my_ts = sc.get("ts", 0)
            my_lamp = sc.get("lamp", "-")
            my_rate = t_prof.get(key, 0)
            matrix_data = matrix_lookup.get(key, []) if matrix_lookup else []

            # SS -> SSS 狙い (現状 TS < 1,000,000)
            if my_ts < 1000000:
                rec_rank_sss.append({
                    "key": key,
                    "title": music["title"],
                    "version": music.get("version", "Unknown"),
                    "constant": music["constant"],
                    "my_rate": my_rate,
                    "my_ts": my_ts,
                    "my_lamp": my_lamp,
                    "target_score": 1000000,
                    "target_rank": "SSS",
                    "diff_to_target": 1000000 - my_ts,
                    "achievement_rate": sss_rate,
                    "adopt_rate": sss_rate,
                    "rate_matrix": matrix_data
                })

            # SSS -> SSS+ 狙い (現状 1,000,000 <= TS < 1,007,500)
            if 1000000 <= my_ts < 1007500:
                rec_rank_sssp.append({
                    "key": key,
                    "title": music["title"],
                    "version": music.get("version", "Unknown"),
                    "constant": music["constant"],
                    "my_rate": my_rate,
                    "my_ts": my_ts,
                    "my_lamp": my_lamp,
                    "target_score": 1007500,
                    "target_rank": "SSS+",
                    "diff_to_target": 1007500 - my_ts,
                    "achievement_rate": sssp_rate,
                    "adopt_rate": sssp_rate,
                    "rate_matrix": matrix_data
                })

            # FC 狙い (自分が FC / AB 未達成)
            is_my_fc = ("FC" in my_lamp) or ("AB" in my_lamp)
            if not is_my_fc:
                rec_lamp_fc.append({
                    "key": key,
                    "title": music["title"],
                    "version": music.get("version", "Unknown"),
                    "constant": music["constant"],
                    "my_rate": my_rate,
                    "my_ts": my_ts,
                    "my_lamp": my_lamp,
                    "target_rank": "FC",
                    "achievement_rate": fc_rate,
                    "adopt_rate": fc_rate,
                    "rate_matrix": matrix_data
                })

            # AB 狙い (自分が AB 未達成)
            is_my_ab = "AB" in my_lamp
            if not is_my_ab:
                rec_lamp_ab.append({
                    "key": key,
                    "title": music["title"],
                    "version": music.get("version", "Unknown"),
                    "constant": music["constant"],
                    "my_rate": my_rate,
                    "my_ts": my_ts,
                    "my_lamp": my_lamp,
                    "target_rank": "AB",
                    "achievement_rate": ab_rate,
                    "adopt_rate": ab_rate,
                    "rate_matrix": matrix_data
                })

        rec_rank_sss.sort(key=lambda x: (x["my_ts"] >= 990000, x["achievement_rate"], x["my_ts"]), reverse=True)
        rec_rank_sssp.sort(key=lambda x: (x["achievement_rate"], x["my_ts"]), reverse=True)
        rec_lamp_fc.sort(key=lambda x: (x["achievement_rate"], x["my_ts"]), reverse=True)
        rec_lamp_ab.sort(key=lambda x: (x["achievement_rate"], x["my_ts"]), reverse=True)

        return {
            "border_new": border_new,
            "border_best": border_best,
            "border_ps": border_ps,
            "rec_new": rec_new[:15],
            "rec_best": rec_best[:50],
            "rec_ps": rec_ps[:30],
            "weapons": weapons,
            "rec_sim": rec_sim[:30],
            "rec_rank_sss": rec_rank_sss[:150],
            "rec_rank_sssp": rec_rank_sssp[:150],
            "rec_lamp_fc": rec_lamp_fc[:150],
            "rec_lamp_ab": rec_lamp_ab[:150]
        }

    def compute_all_group_stats(self):
        groups = [
            ("pm025", "±0.25 (同格)", self.users_data_025),
            ("pm050", "±0.50 (周辺)", self.users_data_050),
            ("p050", "+0.50 (格上)", self.users_data_p050),
        ]
        matrix_lookup = {}
        for group_id, group_label, group_users in groups:
            total_u = len(group_users) if len(group_users) > 0 else 1
            stats = {}
            for uid, data in group_users.items():
                u_scores = data.get("scores", {})
                for key, sc in u_scores.items():
                    ts = sc.get("ts", 0)
                    lamp = sc.get("lamp", "")
                    if ts <= 0:
                        continue
                    if key not in stats:
                        stats[key] = {"ss_count": 0, "sss_count": 0, "sssp_count": 0, "fc_count": 0, "ab_count": 0}
                    if ts >= 990000:
                        stats[key]["ss_count"] += 1
                    if ts >= 1000000:
                        stats[key]["sss_count"] += 1
                    if ts >= 1007500:
                        stats[key]["sssp_count"] += 1
                    if "FC" in lamp or "AB" in lamp:
                        stats[key]["fc_count"] += 1
                    if "AB" in lamp:
                        stats[key]["ab_count"] += 1

            for key in self.music_dict.keys():
                if key not in matrix_lookup:
                    matrix_lookup[key] = []
                st = stats.get(key, {"ss_count": 0, "sss_count": 0, "sssp_count": 0, "fc_count": 0, "ab_count": 0})
                matrix_lookup[key].append({
                    "group_id": group_id,
                    "group_label": group_label,
                    "ss_rate": st["ss_count"] / total_u,
                    "sss_rate": st["sss_count"] / total_u,
                    "sssp_rate": st["sssp_count"] / total_u,
                    "fc_rate": st["fc_count"] / total_u,
                    "ab_rate": st["ab_count"] / total_u
                })
        return matrix_lookup

    def compute_my_data_stats(self):
        if not hasattr(self, 'target_data') or not self.target_data:
            return {}

        scores = self.target_data.get("scores", {})
        total_played = len(scores)

        ab_plus_count = 0
        ab_count = 0
        fc_count = 0
        clear_count = 0

        sssp_count = 0
        sss_count = 0
        ss_count = 0
        s_count = 0
        other_count = 0

        for key, sc in scores.items():
            lamp = sc.get("lamp", "")
            ts = sc.get("ts", 0)

            is_ab = "AB" in lamp
            is_fb = "FB" in lamp
            is_fc = "FC" in lamp or is_fb

            if ts >= 1010000 or "AB+" in lamp:
                ab_plus_count += 1
            elif is_ab:
                ab_count += 1
            elif is_fc:
                fc_count += 1
            else:
                clear_count += 1

            if ts >= 1007500:
                sssp_count += 1
            elif ts >= 1000000:
                sss_count += 1
            elif ts >= 990000:
                ss_count += 1
            elif ts >= 970000:
                s_count += 1
            else:
                other_count += 1

        lamp_stats = {
            "total_played": total_played,
            "ab_plus": {"count": ab_plus_count, "rate": ab_plus_count / total_played if total_played else 0},
            "ab": {"count": ab_count, "rate": ab_count / total_played if total_played else 0},
            "fc": {"count": fc_count, "rate": fc_count / total_played if total_played else 0},
            "clear": {"count": clear_count, "rate": clear_count / total_played if total_played else 0}
        }

        rank_stats = {
            "sssp": {"count": sssp_count, "rate": sssp_count / total_played if total_played else 0},
            "sss": {"count": sss_count, "rate": sss_count / total_played if total_played else 0},
            "ss": {"count": ss_count, "rate": ss_count / total_played if total_played else 0},
            "s": {"count": s_count, "rate": s_count / total_played if total_played else 0},
            "other": {"count": other_count, "rate": other_count / total_played if total_played else 0}
        }

        level_groups = ["12", "12+", "13", "13+", "14", "14+", "15"]
        level_stats_map = {lvl: {
            "level": lvl,
            "played_charts": 0,
            "sssp_count": 0,
            "sss_count": 0,
            "fc_count": 0,
            "ab_count": 0,
            "sum_ts": 0
        } for lvl in level_groups}

        for key, sc in scores.items():
            if key not in self.music_dict:
                continue
            m = self.music_dict[key]
            lvl = m.get("level", "")

            if lvl in level_stats_map:
                st = level_stats_map[lvl]
                st["played_charts"] += 1
                ts = sc.get("ts", 0)
                lamp = sc.get("lamp", "")
                st["sum_ts"] += ts
                if ts >= 1007500:
                    st["sssp_count"] += 1
                if ts >= 1000000:
                    st["sss_count"] += 1
                if "FC" in lamp or "AB" in lamp:
                    st["fc_count"] += 1
                if "AB" in lamp:
                    st["ab_count"] += 1

        level_matrix = []
        for lvl in level_groups:
            st = level_stats_map[lvl]
            played = st["played_charts"]
            if played == 0:
                continue
            level_matrix.append({
                "level": lvl,
                "played_charts": played,
                "sssp_count": st["sssp_count"],
                "sssp_rate": st["sssp_count"] / played if played else 0,
                "sss_count": st["sss_count"],
                "sss_rate": st["sss_count"] / played if played else 0,
                "fc_count": st["fc_count"],
                "fc_rate": st["fc_count"] / played if played else 0,
                "ab_count": st["ab_count"],
                "ab_rate": st["ab_count"] / played if played else 0,
                "avg_ts": round(st["sum_ts"] / played) if played else 0
            })

        return {
            "total_played": total_played,
            "lamp_stats": lamp_stats,
            "rank_stats": rank_stats,
            "level_matrix": level_matrix
        }

    def analyze(self):
        matrix_lookup = self.compute_all_group_stats()
        res_025 = self.analyze_group(self.users_data_025, matrix_lookup)
        res_050 = self.analyze_group(self.users_data_050, matrix_lookup)
        res_p050 = self.analyze_group(self.users_data_p050, matrix_lookup)
        
        export_data = {
            "target_user": self.target_user_id,
            "borders": {
                "new": res_025["border_new"],
                "best": res_025["border_best"],
                "ps": res_025["border_ps"]
            },
            "results": {
                "pm025": res_025,
                "pm050": res_050,
                "p050": res_p050
            },
            "my_data": self.compute_my_data_stats(),
            "last_updated": "2026-09-08"
        }
        
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "public", "data")
        if os.path.exists(os.path.dirname(out_dir)):
            os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, "recommend_data.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            print(f"Exported advanced recommendation data to {out_file}")
            
        return export_data

if __name__ == "__main__":
    engine = RecommendEngine()
    engine.analyze()
