import { useState, useMemo, useEffect } from 'react';
import ExportControls from './ExportControls';
import { Target, Users, Flame, Activity, Music, ArrowUp, ArrowDown, Search, Trophy, BarChart2, Lock, LogOut } from 'lucide-react';
import './App.css';

type RateMatrixItem = {
  group_id: string;
  group_label: string;
  ss_rate: number;
  sss_rate: number;
  sssp_rate: number;
  fc_rate: number;
  ab_rate: number;
};

type RecommendItem = {
  key: string;
  title: string;
  version: string;
  adopt_rate: number;
  expected_rate?: number;
  my_rate?: number;
  my_ts?: number;
  target_score?: number;
  target_star?: number;
  my_star?: number;
  my_lamp?: string;
  constant: number;
  target_rank?: string;
  diff_to_target?: number;
  achievement_rate?: number;
  rate_matrix?: RateMatrixItem[];
};

type LampStatItem = { count: number; rate: number };
type RankStatItem = { count: number; rate: number };

type LevelMatrixItem = {
  level: string;
  total_charts: number;
  played_charts: number;
  played_rate: number;
  sssp_count: number;
  sssp_rate: number;
  sss_count: number;
  sss_rate: number;
  fc_count: number;
  fc_rate: number;
  ab_count: number;
  ab_rate: number;
  avg_ts: number;
};

type MyDataStats = {
  total_played: number;
  lamp_stats: {
    total_played: number;
    ab_plus: LampStatItem;
    ab: LampStatItem;
    fc: LampStatItem;
    clear: LampStatItem;
  };
  rank_stats: {
    sssp: RankStatItem;
    sss: RankStatItem;
    ss: RankStatItem;
    s: RankStatItem;
    other: RankStatItem;
  };
  level_matrix: LevelMatrixItem[];
  level_matrix_by_diff?: {
    all: LevelMatrixItem[];
    master_luna: LevelMatrixItem[];
    master: LevelMatrixItem[];
    expert: LevelMatrixItem[];
  };
};

type GroupResult = {
  border_new: number;
  border_best: number;
  border_ps: number;
  rec_new: RecommendItem[];
  rec_best: RecommendItem[];
  rec_ps: RecommendItem[];
  weapons: RecommendItem[];
  rec_sim: RecommendItem[];
  rec_rank_sss?: RecommendItem[];
  rec_rank_sssp?: RecommendItem[];
  rec_lamp_fc?: RecommendItem[];
  rec_lamp_ab?: RecommendItem[];
};

type AppData = {
  target_user: string;
  borders: { new: number; best: number; ps: number };
  results: {
    pm025: GroupResult;
    pm050: GroupResult;
    p050: GroupResult;
  };
  my_data?: MyDataStats;
};

function App() {
  const [passcode, setPasscode] = useState<string>(() => localStorage.getItem('ongeki_passcode') || '');
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => localStorage.getItem('ongeki_passcode') === '123123');
  const [passcodeInput, setPasscodeInput] = useState<string>('');
  const [passcodeError, setPasscodeError] = useState<string>('');

  const [userIdInput, setUserIdInput] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [data, setData] = useState<AppData | null>(null);
  const [activeTab, setActiveTab] = useState<'new' | 'best' | 'ps' | 'similar' | 'weapons' | 'rank' | 'mydata'>('best');
  const [rankSubTab, setRankSubTab] = useState<'sss' | 'sssp' | 'fc' | 'ab'>('sss');
  const [constantFilter, setConstantFilter] = useState<'all' | '13.0' | '13.7' | '14.0'>('13.7');
  const [group, setGroup] = useState<'pm025' | 'pm050' | 'p050'>('pm025');
  const [sortConfig, setSortConfig] = useState<{ key: keyof RecommendItem; direction: 'asc' | 'desc' } | null>(null);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    const checkStatus = () => {
      fetch('/api/update_status')
        .then(res => res.json())
        .then(data => setIsUpdating(data.is_running))
        .catch(() => {});
    };
    checkStatus();
    const interval = setInterval(checkStatus, 3000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  const handlePasscodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasscodeError('');
    const code = passcodeInput.trim();
    if (!code) {
      setPasscodeError('合言葉を入力してください');
      return;
    }

    try {
      const res = await fetch('/api/verify_passcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode: code })
      });
      if (res.ok) {
        localStorage.setItem('ongeki_passcode', code);
        setPasscode(code);
        setIsAuthenticated(true);
        setPasscodeInput('');
      } else {
        setPasscodeError('合言葉が違います');
      }
    } catch {
      // ネットワークや起動ラグ時のフォールバック
      if (code === '123123') {
        localStorage.setItem('ongeki_passcode', '123123');
        setPasscode('123123');
        setIsAuthenticated(true);
        setPasscodeInput('');
      } else {
        setPasscodeError('合言葉が違います');
      }
    }
  };

  const handleLogout = () => {
    if (window.confirm('合言葉を解除してロックしますか？')) {
      localStorage.removeItem('ongeki_passcode');
      setPasscode('');
      setIsAuthenticated(false);
      setData(null);
    }
  };

  const fetchUserData = (userId: string) => {
    setLoading(true);
    fetch(`/api/recommend/${userId}`, {
      headers: { 'X-Passcode': passcode }
    })
      .then(async res => {
        if (res.status === 401) {
          localStorage.removeItem('ongeki_passcode');
          setIsAuthenticated(false);
          throw new Error('合言葉が無効です。もう一度合言葉を入力してください。');
        }
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          const msg = errData.detail || `エラー (${res.status}): データの取得に失敗しました`;
          throw new Error(msg);
        }
        return res.json();
      })
      .then(d => {
        setData(d);
        if (activeTab === 'weapons') {
          setSortConfig({ key: 'adopt_rate', direction: 'asc' });
        }
      })
      .catch(e => {
        console.error(e);
        alert(e.message || 'データ取得に失敗しました。');
      })
      .finally(() => setLoading(false));
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (userIdInput.trim()) fetchUserData(userIdInput.trim());
  };

  const handleUpdateCache = async (minRating: number) => {
    if (!window.confirm("最新の他ユーザーデータを取得・更新しますか？\n（処理完了まで数分かかります）")) {
      return;
    }
    try {
      const res = await fetch('/api/update_cache', { 
        method: 'POST', 
        headers: {
          'Content-Type': 'application/json',
          'X-Passcode': passcode
        }, 
        body: JSON.stringify({ min_rating: minRating }) 
      });
      if (res.ok) {
        setIsUpdating(true);
        alert("バックグラウンド更新を開始しました。");
      } else if (res.status === 401) {
        setIsAuthenticated(false);
        alert("合言葉が無効です。");
      }
    } catch (e) {
      alert("更新の開始に失敗しました。");
    }
  };

  const handleStopUpdate = async () => {
    try {
      const res = await fetch('/api/stop_update', { 
        method: 'POST',
        headers: { 'X-Passcode': passcode }
      });
      if (res.ok) {
        alert("更新の停止をリクエストしました。");
      }
    } catch (e) {
      alert("停止リクエストに失敗しました。");
    }
  };

  const handleSort = (key: keyof RecommendItem) => {
    let direction: 'desc' | 'asc' = 'desc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc';
    }
    setSortConfig({ key, direction });
  };

  const formatLamp = (lamp: string | undefined) => {
    if (!lamp || lamp === '-') return null;
    let cleaned = lamp;
    if (cleaned.includes('FB') && cleaned.includes('FC')) {
      cleaned = cleaned.replace('+FC', '').replace('FC+', '').replace('FC', '');
    }
    return cleaned;
  };

  const currentResult = data ? data.results[group] : null;
  let items: RecommendItem[] = [];
  if (currentResult) {
    switch (activeTab) {
      case 'new': items = currentResult.rec_new; break;
      case 'best': items = currentResult.rec_best; break;
      case 'ps': items = currentResult.rec_ps; break;
      case 'similar': items = currentResult.rec_sim; break;
      case 'weapons': items = currentResult.weapons; break;
      case 'rank':
        if (rankSubTab === 'sss') items = currentResult.rec_rank_sss || [];
        else if (rankSubTab === 'sssp') items = currentResult.rec_rank_sssp || [];
        else if (rankSubTab === 'fc') items = currentResult.rec_lamp_fc || [];
        else if (rankSubTab === 'ab') items = currentResult.rec_lamp_ab || [];
        break;
    }
  }

  const filteredItems = useMemo(() => {
    if (activeTab !== 'rank') return items;
    if (constantFilter === '13.0') return items.filter(i => i.constant >= 13.0);
    if (constantFilter === '13.7') return items.filter(i => i.constant >= 13.7);
    if (constantFilter === '14.0') return items.filter(i => i.constant >= 14.0);
    return items;
  }, [items, activeTab, constantFilter]);

  const sortedItems = useMemo(() => {
    if (!sortConfig) return filteredItems;
    return [...filteredItems].sort((a, b) => {
      const aVal = a[sortConfig.key] ?? 0;
      const bVal = b[sortConfig.key] ?? 0;
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredItems, sortConfig]);

  const TabButton = ({ id, icon: Icon, label }: { id: typeof activeTab, icon: any, label: string }) => (
    <button
      onClick={() => {
        setActiveTab(id);
        if (id === 'weapons') {
          setSortConfig({ key: 'adopt_rate', direction: 'asc' });
        } else {
          setSortConfig(null);
        }
      }}
      className={`flex-shrink-0 sm:flex-1 flex flex-col sm:flex-row items-center justify-center py-2.5 px-3 sm:px-4 border-b-2 transition-all whitespace-nowrap gap-1 sm:gap-1.5 ${
        activeTab === id 
          ? 'border-blue-600 text-blue-600 font-bold bg-blue-50/50' 
          : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-50'
      }`}
    >
      <Icon className="w-4 h-4 shrink-0" />
      <span className="text-xs font-semibold">{label}</span>
    </button>
  );

  const Th = ({ label, sortKey }: { label: string, sortKey: keyof RecommendItem }) => (
    <th 
      className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
      onClick={() => handleSort(sortKey)}
    >
      <div className="flex items-center gap-1">
        {label}
        {sortConfig?.key === sortKey && (
          sortConfig.direction === 'asc' ? <ArrowUp className="w-3 h-3 text-blue-500" /> : <ArrowDown className="w-3 h-3 text-blue-500" />
        )}
      </div>
    </th>
  );

  const isPs = activeTab === 'ps';
  const isWeapons = activeTab === 'weapons';
  const isRank = activeTab === 'rank';

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-900 via-indigo-900 to-purple-900 flex items-center justify-center p-4 font-sans">
        <div className="bg-white p-8 rounded-2xl shadow-2xl max-w-sm w-full text-center border border-blue-100">
          <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mx-auto mb-4 shadow-inner">
            <Lock size={32} />
          </div>
          <h1 className="text-2xl font-black text-gray-900 mb-2">Ongeki Target Finder</h1>
          <p className="text-sm text-gray-600 mb-6">
            友人限定公開のツールです。<br />利用するには合言葉を入力してください。
          </p>
          <form onSubmit={handlePasscodeSubmit} className="space-y-4">
            <div>
              <input
                type="password"
                placeholder="合言葉を入力"
                value={passcodeInput}
                onChange={(e) => setPasscodeInput(e.target.value)}
                autoFocus
                className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl text-center text-lg font-mono tracking-widest focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all text-gray-800"
              />
              {passcodeError && (
                <p className="text-red-500 text-sm mt-2 font-medium">{passcodeError}</p>
              )}
            </div>
            <button
              type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-lg hover:shadow-xl transition-all flex items-center justify-center gap-2"
            >
              <span>ロックを解除して開始</span>
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20 font-sans">
      <header className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white py-3 px-3 sm:py-4 sm:px-4 shadow-sm">
        <div className="max-w-5xl mx-auto flex flex-col gap-2.5 sm:gap-3">
          {/* 上段: タイトル & 検索フォーム */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2.5">
            <div className="flex items-center justify-between w-full sm:w-auto">
              <div className="flex items-center gap-2.5">
                <div>
                  <h1 className="text-lg sm:text-xl font-bold tracking-tight">Ongeki Target Finder</h1>
                  {data && <div className="text-[11px] text-blue-200">User ID: <span className="text-white font-mono font-bold">{data.target_user}</span></div>}
                </div>
                <button
                  onClick={handleLogout}
                  title="ログアウト（合言葉解除）"
                  className="p-1 rounded-md bg-white/10 hover:bg-white/20 text-blue-200 hover:text-white transition-colors text-xs flex items-center gap-1"
                >
                  <LogOut size={13} />
                </button>
              </div>
            </div>

            <form onSubmit={handleSearch} className="flex gap-1.5 w-full sm:w-auto">
              <input 
                type="text" 
                placeholder="User IDを入力 (例: 10605)" 
                value={userIdInput}
                onChange={(e) => setUserIdInput(e.target.value)}
                className="bg-blue-50 border border-blue-200 px-3 py-1.5 rounded-lg text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 flex-1 sm:w-44 placeholder-gray-400"
              />
              <button 
                type="submit"
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-1 disabled:opacity-50 whitespace-nowrap shadow-sm"
              >
                <Search size={15} />
                {loading ? '検索中...' : '検索'}
              </button>
            </form>
          </div>

          {/* 下段: ステータス・ボーダー・操作コントロール */}
          {data && (
            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-white/10 text-xs">
              <div className="flex gap-3 bg-black/20 px-2.5 py-1 rounded-lg shadow-inner">
                <div className="flex flex-col items-center"><span className="text-blue-200 text-[10px]">New</span><strong className="font-mono">{data.borders.new.toFixed(2)}</strong></div>
                <div className="flex flex-col items-center"><span className="text-blue-200 text-[10px]">Best</span><strong className="font-mono">{data.borders.best.toFixed(2)}</strong></div>
                <div className="flex flex-col items-center"><span className="text-blue-200 text-[10px]">PS(★)</span><strong className="font-mono">{data.borders.ps}</strong></div>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 bg-white text-gray-800 px-2.5 py-1 rounded-lg shadow-sm">
                  <span className="text-[10px] text-gray-500 font-medium">比較:</span>
                  <select 
                    value={group} 
                    onChange={e => setGroup(e.target.value as any)}
                    className="bg-transparent font-bold outline-none cursor-pointer text-xs"
                  >
                    <option value="pm025">±0.25</option>
                    <option value="pm050">±0.5</option>
                    <option value="p050">+0.5</option>
                  </select>
                </div>
                <ExportControls 
                  items={sortedItems} 
                  activeTab={activeTab} 
                  tableId="recommend-table" 
                  groupLabel={group === "pm025" ? "±0.25" : group === "pm050" ? "±0.5" : "+0.5"}
                />
              </div>

              {isUpdating ? (
                <button 
                  onClick={handleStopUpdate}
                  className="bg-red-600 hover:bg-red-500 text-white px-2 py-1 rounded-md text-[11px] font-medium transition-colors border border-red-400 whitespace-nowrap animate-pulse shadow-sm"
                >
                  更新停止
                </button>
              ) : (
                <div className="flex gap-1.5 ml-auto sm:ml-0">
                  <button 
                    onClick={() => handleUpdateCache(19.0)}
                    className="bg-white/10 hover:bg-white/20 text-white px-2 py-1 rounded-md text-[11px] font-medium transition-colors border border-white/20 whitespace-nowrap"
                  >
                    19.0+更新
                  </button>
                  <button 
                    onClick={() => handleUpdateCache(18.0)}
                    className="bg-white/10 hover:bg-white/20 text-white px-2 py-1 rounded-md text-[11px] font-medium transition-colors border border-white/20 whitespace-nowrap"
                  >
                    18.0+更新
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {!data && !loading && (
        <div className="flex h-[50vh] items-center justify-center text-gray-500 text-sm">
          User IDを入力して検索してください。
        </div>
      )}

      {/* タブバー: 画面上部 (top-0) にSticky吸着 */}
      {data && (
        <div className="sticky top-0 z-30 bg-white/95 backdrop-blur-md shadow-sm border-b border-gray-200">
          <div className="max-w-5xl mx-auto px-2 sm:px-4 flex overflow-x-auto justify-start sm:justify-center">
            <TabButton id="new" icon={Music} label="新曲枠(15曲)" />
            <TabButton id="best" icon={Target} label="ベスト枠(50曲)" />
            <TabButton id="ps" icon={Activity} label="Pスコア枠(30曲)" />
            <TabButton id="similar" icon={Users} label="類似プレイヤー" />
            <TabButton id="weapons" icon={Flame} label="逆リコメンド" />
            <TabButton id="rank" icon={Trophy} label="目標達成" />
            <TabButton id="mydata" icon={BarChart2} label="マイデータ" />
          </div>
        </div>
      )}

      {data && (
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          {activeTab === 'rank' && (
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-3 mb-1">
              <div className="flex flex-wrap justify-center gap-1.5 bg-gray-200/70 p-1 rounded-full shadow-inner">
                <button
                  onClick={() => setRankSubTab('sss')}
                  className={`px-3 py-1 rounded-full text-xs font-bold transition-colors ${
                    rankSubTab === 'sss'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  SS → SSS
                </button>
                <button
                  onClick={() => setRankSubTab('sssp')}
                  className={`px-3 py-1 rounded-full text-xs font-bold transition-colors ${
                    rankSubTab === 'sssp'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  SSS → SSS+
                </button>
                <button
                  onClick={() => setRankSubTab('fc')}
                  className={`px-3 py-1 rounded-full text-xs font-bold transition-colors ${
                    rankSubTab === 'fc'
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  FC 狙い
                </button>
                <button
                  onClick={() => setRankSubTab('ab')}
                  className={`px-3 py-1 rounded-full text-xs font-bold transition-colors ${
                    rankSubTab === 'ab'
                      ? 'bg-amber-600 text-white shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  AB 狙い
                </button>
              </div>

              <div className="flex items-center gap-1 bg-white border border-gray-300 px-2 py-1 rounded-full text-xs shadow-sm">
                <span className="text-gray-500 font-medium ml-1">定数:</span>
                {(['13.0', '13.7', '14.0', 'all'] as const).map(cf => (
                  <button
                    key={cf}
                    onClick={() => setConstantFilter(cf)}
                    className={`px-2 py-0.5 rounded-full font-bold transition-colors ${
                      constantFilter === cf
                        ? 'bg-gray-800 text-white'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {cf === 'all' ? '全曲' : `${cf}+`}
                  </button>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'mydata' && data.my_data && (
            <div className="bg-white rounded-b-lg p-6 shadow-sm flex flex-col gap-8 my-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 p-4 rounded-xl shadow-xs">
                  <div className="text-xs text-blue-600 font-semibold mb-1">総プレイ譜面数</div>
                  <div className="text-2xl font-extrabold text-gray-900 font-mono">
                    {data.my_data.total_played} <span className="text-xs font-normal text-gray-500">譜面</span>
                  </div>
                </div>
                <div className="bg-gradient-to-br from-amber-50 to-yellow-50 border border-amber-100 p-4 rounded-xl shadow-xs">
                  <div className="text-xs text-amber-700 font-semibold mb-1">ALL BREAK (AB/AB+)</div>
                  <div className="text-2xl font-extrabold text-amber-700 font-mono">
                    {data.my_data.lamp_stats.ab_plus.count + data.my_data.lamp_stats.ab.count} <span className="text-xs font-normal text-gray-500">譜面</span>
                  </div>
                </div>
                <div className="bg-gradient-to-br from-purple-50 to-indigo-50 border border-purple-100 p-4 rounded-xl shadow-xs">
                  <div className="text-xs text-purple-700 font-semibold mb-1">SSS / SSS+ 達成</div>
                  <div className="text-2xl font-extrabold text-purple-700 font-mono">
                    {data.my_data.rank_stats.sssp.count + data.my_data.rank_stats.sss.count} <span className="text-xs font-normal text-gray-500">譜面</span>
                  </div>
                </div>
                <div className="bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100 p-4 rounded-xl shadow-xs">
                  <div className="text-xs text-emerald-700 font-semibold mb-1">FULL COMBO (FC+)</div>
                  <div className="text-2xl font-extrabold text-emerald-700 font-mono">
                    {data.my_data.lamp_stats.ab_plus.count + data.my_data.lamp_stats.ab.count + data.my_data.lamp_stats.fc.count} <span className="text-xs font-normal text-gray-500">譜面</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-gray-50 border border-gray-200 p-5 rounded-2xl">
                  <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <span className="w-2 h-4 bg-amber-500 rounded-sm"></span>
                    クリアランプ達成分布
                  </h3>
                  <div className="w-full h-4 bg-gray-200 rounded-full overflow-hidden flex mb-4 shadow-inner">
                    <div style={{ width: `${data.my_data.lamp_stats.ab_plus.rate * 100}%` }} className="bg-yellow-400 h-full" title={`AB+: ${(data.my_data.lamp_stats.ab_plus.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.lamp_stats.ab.rate * 100}%` }} className="bg-amber-500 h-full" title={`AB: ${(data.my_data.lamp_stats.ab.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.lamp_stats.fc.rate * 100}%` }} className="bg-emerald-500 h-full" title={`FC: ${(data.my_data.lamp_stats.fc.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.lamp_stats.clear.rate * 100}%` }} className="bg-sky-400 h-full" title={`CLEAR: ${(data.my_data.lamp_stats.clear.rate * 100).toFixed(1)}%`} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="flex justify-between items-center bg-white p-2.5 rounded-lg border border-gray-100 shadow-2xs">
                      <span className="flex items-center gap-1.5 font-bold text-yellow-600">
                        <span className="w-2 h-2 rounded-full bg-yellow-400"></span>ALL BREAK+
                      </span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.lamp_stats.ab_plus.count} <span className="text-[10px] text-gray-400">({(data.my_data.lamp_stats.ab_plus.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                    <div className="flex justify-between items-center bg-white p-2.5 rounded-lg border border-gray-100 shadow-2xs">
                      <span className="flex items-center gap-1.5 font-bold text-amber-600">
                        <span className="w-2 h-2 rounded-full bg-amber-500"></span>ALL BREAK
                      </span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.lamp_stats.ab.count} <span className="text-[10px] text-gray-400">({(data.my_data.lamp_stats.ab.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                    <div className="flex justify-between items-center bg-white p-2.5 rounded-lg border border-gray-100 shadow-2xs">
                      <span className="flex items-center gap-1.5 font-bold text-emerald-600">
                        <span className="w-2 h-2 rounded-full bg-emerald-500"></span>FULL COMBO
                      </span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.lamp_stats.fc.count} <span className="text-[10px] text-gray-400">({(data.my_data.lamp_stats.fc.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                    <div className="flex justify-between items-center bg-white p-2.5 rounded-lg border border-gray-100 shadow-2xs">
                      <span className="flex items-center gap-1.5 font-bold text-sky-600">
                        <span className="w-2 h-2 rounded-full bg-sky-400"></span>CLEAR
                      </span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.lamp_stats.clear.count} <span className="text-[10px] text-gray-400">({(data.my_data.lamp_stats.clear.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 border border-gray-200 p-5 rounded-2xl">
                  <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <span className="w-2 h-4 bg-purple-600 rounded-sm"></span>
                    スコアランク達成分布
                  </h3>
                  <div className="w-full h-4 bg-gray-200 rounded-full overflow-hidden flex mb-4 shadow-inner">
                    <div style={{ width: `${data.my_data.rank_stats.sssp.rate * 100}%` }} className="bg-purple-600 h-full" title={`SSS+: ${(data.my_data.rank_stats.sssp.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.rank_stats.sss.rate * 100}%` }} className="bg-indigo-500 h-full" title={`SSS: ${(data.my_data.rank_stats.sss.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.rank_stats.ss.rate * 100}%` }} className="bg-sky-400 h-full" title={`SS: ${(data.my_data.rank_stats.ss.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.rank_stats.s.rate * 100}%` }} className="bg-emerald-400 h-full" title={`S: ${(data.my_data.rank_stats.s.rate * 100).toFixed(1)}%`} />
                    <div style={{ width: `${data.my_data.rank_stats.other.rate * 100}%` }} className="bg-gray-300 h-full" title={`Other: ${(data.my_data.rank_stats.other.rate * 100).toFixed(1)}%`} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="flex justify-between items-center bg-white p-2 border border-gray-100 rounded-lg shadow-2xs">
                      <span className="flex items-center gap-1 font-bold text-purple-600"><span className="w-2 h-2 rounded-full bg-purple-600"></span>SSS+</span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.rank_stats.sssp.count} <span className="text-[10px] text-gray-400">({(data.my_data.rank_stats.sssp.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                    <div className="flex justify-between items-center bg-white p-2 border border-gray-100 rounded-lg shadow-2xs">
                      <span className="flex items-center gap-1 font-bold text-indigo-600"><span className="w-2 h-2 rounded-full bg-indigo-500"></span>SSS</span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.rank_stats.sss.count} <span className="text-[10px] text-gray-400">({(data.my_data.rank_stats.sss.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                    <div className="flex justify-between items-center bg-white p-2 border border-gray-100 rounded-lg shadow-2xs">
                      <span className="flex items-center gap-1 font-bold text-sky-600"><span className="w-2 h-2 rounded-full bg-sky-400"></span>SS</span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.rank_stats.ss.count} <span className="text-[10px] text-gray-400">({(data.my_data.rank_stats.ss.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                    <div className="flex justify-between items-center bg-white p-2 border border-gray-100 rounded-lg shadow-2xs">
                      <span className="flex items-center gap-1 font-bold text-emerald-600"><span className="w-2 h-2 rounded-full bg-emerald-400"></span>S</span>
                      <span className="font-mono font-bold text-gray-800">{data.my_data.rank_stats.s.count} <span className="text-[10px] text-gray-400">({(data.my_data.rank_stats.s.rate * 100).toFixed(1)}%)</span></span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 border border-gray-200 p-5 rounded-2xl">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-2 border-b border-gray-200">
                  <div>
                    <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                      <span className="w-2.5 h-5 bg-blue-600 rounded-sm"></span>
                      レベル別達成状況
                    </h3>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-gray-100/80 text-gray-600 font-semibold border-b border-gray-200">
                        <th className="py-2.5 px-3">レベル</th>
                        <th className="py-2.5 px-3 font-mono">プレイ譜面数</th>
                        <th className="py-2.5 px-3 min-w-[190px]">SSS / SSS+ 達成率</th>
                        <th className="py-2.5 px-3 min-w-[190px]">FC / AB 達成率</th>
                        <th className="py-2.5 px-3 text-right">平均スコア</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200/70 bg-white">
                      {data.my_data.level_matrix.filter(row => !['10', '10+', '11', '11+', 'Lunatic'].includes(row.level)).map((row) => {
                        const sssPct = (row.sss_rate * 100).toFixed(1);
                        const ssspPct = (row.sssp_rate * 100).toFixed(1);
                        const fcPct = (row.fc_rate * 100).toFixed(1);
                        const abPct = (row.ab_rate * 100).toFixed(1);

                        return (
                          <tr key={row.level} className="hover:bg-blue-50/30 transition-colors">
                            <td className="py-3 px-3">
                              <span className={`inline-block px-2.5 py-1 rounded-md font-bold font-mono text-xs ${
                                row.level.includes('+')
                                  ? 'bg-blue-900 text-blue-100'
                                  : 'bg-blue-100 text-blue-800'
                              }`}>
                                Lv {row.level}
                              </span>
                            </td>
                            
                            <td className="py-3 px-3 font-mono font-bold text-gray-800 text-xs">
                              {row.played_charts} <span className="text-gray-400 font-normal">譜面</span>
                            </td>

                            <td className="py-3 px-3">
                              <div className="flex justify-between text-[11px] font-mono mb-1">
                                <span className="text-indigo-600 font-bold">SSS: {row.sss_count} <span className="text-[10px] text-indigo-400">({sssPct}%)</span></span>
                                <span className="text-purple-600 font-bold">SSS+: {row.sssp_count} <span className="text-[10px] text-purple-400">({ssspPct}%)</span></span>
                              </div>
                              <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden border border-gray-200 flex">
                                <div style={{ width: `${ssspPct}%` }} className="bg-purple-600 h-full" title={`SSS+: ${ssspPct}%`} />
                                <div style={{ width: `${Math.max(0, parseFloat(sssPct) - parseFloat(ssspPct))}%` }} className="bg-indigo-400 h-full" title={`SSS: ${sssPct}%`} />
                              </div>
                            </td>

                            <td className="py-3 px-3">
                              <div className="flex justify-between text-[11px] font-mono mb-1">
                                <span className="text-emerald-600 font-bold">FC: {row.fc_count} <span className="text-[10px] text-emerald-400">({fcPct}%)</span></span>
                                <span className="text-amber-600 font-bold">AB: {row.ab_count} <span className="text-[10px] text-amber-400">({abPct}%)</span></span>
                              </div>
                              <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden border border-gray-200 flex">
                                <div style={{ width: `${abPct}%` }} className="bg-amber-500 h-full" title={`AB: ${abPct}%`} />
                                <div style={{ width: `${Math.max(0, parseFloat(fcPct) - parseFloat(abPct))}%` }} className="bg-emerald-400 h-full" title={`FC: ${fcPct}%`} />
                              </div>
                            </td>

                            <td className="py-3 px-3 text-right font-mono font-bold text-gray-800 text-xs">
                              {row.avg_ts > 0 ? row.avg_ts.toLocaleString() : '-'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {activeTab !== 'mydata' && (
            <main className="py-4 mx-auto w-full mb-8">
              <div className="bg-white rounded-b-lg shadow ring-1 ring-black ring-opacity-5 overflow-x-auto">
              <table id="recommend-table" className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="w-12 px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">#</th>
                    <Th label="タイトル" sortKey="title" />
                    <Th label="難易度" sortKey="key" />
                    <Th label="定数" sortKey="constant" />
                    
                    {isPs ? (
                      <>
                        <Th label="現状の星" sortKey="my_star" />
                        <Th label="目標の星" sortKey="target_star" />
                        <Th label="期待レート" sortKey="expected_rate" />
                      </>
                    ) : isRank ? (
                      <>
                        <Th label="現状スコア" sortKey="my_ts" />
                        <Th label="目標" sortKey="target_rank" />
                        <Th label="目標まで" sortKey="diff_to_target" />
                      </>
                    ) : (
                      <>
                        <Th label="現状レート" sortKey="my_rate" />
                        {!isWeapons && <Th label="期待レート" sortKey="expected_rate" />}
                        <Th label="現状スコア" sortKey="my_ts" />
                        {!isWeapons && <Th label="目標スコア" sortKey="target_score" />}
                      </>
                    )}
                    <Th label={isRank ? "達成率" : "採用率"} sortKey={isRank ? "achievement_rate" : "adopt_rate"} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {sortedItems.map((item, idx) => {
                    const rateVal = isRank ? (item.achievement_rate ?? 0) : item.adopt_rate;
                    return (
                      <tr key={item.key} className="hover:bg-blue-50 transition-colors">
                        <td className="px-3 py-2 whitespace-nowrap text-center text-xs text-gray-400 font-mono">{idx + 1}</td>
                        <td className="px-3 py-2 min-w-[160px] max-w-[260px] relative group/title">
                          <div className="text-sm font-bold text-gray-900 break-words cursor-pointer hover:text-blue-600 transition-colors">
                            {item.title}
                          </div>
                          <div className="text-[10px] text-gray-500 truncate">{item.version}</div>

                          {isRank && item.rate_matrix && item.rate_matrix.length > 0 && (
                            <div className="hidden group-hover/title:block absolute left-2 top-full mt-1 z-30 w-[360px] p-3 bg-gray-900/95 text-white rounded-xl shadow-2xl backdrop-blur-sm border border-gray-700 pointer-events-none transition-all duration-200">
                              <div className="text-xs font-bold text-blue-300 border-b border-gray-700 pb-1.5 mb-2 flex items-center justify-between">
                                <span className="truncate max-w-[240px]">{item.title}</span>
                                <span className="text-[10px] bg-blue-900/80 text-blue-200 px-1.5 py-0.5 rounded font-mono">定数 {item.constant.toFixed(1)}</span>
                              </div>
                              <table className="w-full text-[11px] font-mono border-collapse">
                                <thead>
                                  <tr className="border-b border-gray-700 text-gray-400 text-[10px]">
                                    <th className="text-left font-sans py-1">比較対象</th>
                                    <th className="text-right py-1 text-sky-400">SS</th>
                                    <th className="text-right py-1 text-indigo-400">SSS</th>
                                    <th className="text-right py-1 text-purple-400">SSS+</th>
                                    <th className="text-right py-1 text-emerald-400">FC</th>
                                    <th className="text-right py-1 text-amber-400">AB</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-800/60">
                                  {item.rate_matrix.map(mat => (
                                    <tr key={mat.group_id} className="hover:bg-white/5">
                                      <td className="py-1 text-left font-sans text-gray-300 font-semibold">{mat.group_label}</td>
                                      <td className="py-1 text-right text-sky-300 font-bold">{(mat.ss_rate * 100).toFixed(1)}%</td>
                                      <td className="py-1 text-right text-indigo-300 font-bold">{(mat.sss_rate * 100).toFixed(1)}%</td>
                                      <td className="py-1 text-right text-purple-300 font-bold">{(mat.sssp_rate * 100).toFixed(1)}%</td>
                                      <td className="py-1 text-right text-emerald-300 font-bold">{(mat.fc_rate * 100).toFixed(1)}%</td>
                                      <td className="py-1 text-right text-amber-300 font-bold">{(mat.ab_rate * 100).toFixed(1)}%</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-700 font-bold">
                          {item.key.split('_')[1]}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-600 font-mono">{item.constant.toFixed(1)}</td>
                        
                        {isPs ? (
                          <>
                            <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500 font-mono">
                              <div className="flex items-center gap-2">
                                <span>{item.my_star ?? 0}</span>
                                {formatLamp(item.my_lamp) && (
                                  <span className="text-[10px] bg-white text-gray-700 px-1 py-0.5 rounded border border-gray-300 shadow-sm leading-none font-sans font-medium tracking-tight">
                                    {formatLamp(item.my_lamp)}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 whitespace-nowrap text-sm font-medium text-blue-600 font-mono">
                              {item.target_star ?? '-'}
                            </td>
                            <td className="px-3 py-2 whitespace-nowrap text-sm font-mono font-bold text-indigo-600">
                              {item.expected_rate ? item.expected_rate.toFixed(3) : '-'}
                            </td>
                          </>
                        ) : isRank ? (
                          <>
                            <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500 font-mono">
                              <div className="flex items-center gap-2">
                                <span>{item.my_ts ? item.my_ts.toLocaleString() : '-'}</span>
                                {formatLamp(item.my_lamp) && (
                                  <span className="text-[10px] bg-white text-gray-700 px-1 py-0.5 rounded border border-gray-300 shadow-sm leading-none font-sans font-medium tracking-tight">
                                    {formatLamp(item.my_lamp)}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 whitespace-nowrap text-sm font-mono font-bold">
                              {item.target_score ? (
                                <span className="text-blue-600">{item.target_score.toLocaleString()} ({item.target_rank})</span>
                              ) : (
                                <span className={`px-2 py-0.5 rounded text-xs ${item.target_rank === 'AB' ? 'bg-amber-100 text-amber-800 border border-amber-300' : 'bg-emerald-100 text-emerald-800 border border-emerald-300'}`}>
                                  {item.target_rank}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2 whitespace-nowrap text-sm font-mono font-bold text-red-500">
                              {item.diff_to_target !== undefined ? `あと ${item.diff_to_target.toLocaleString()} 点` : '-'}
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500 font-mono">
                              <div className="flex items-center gap-2">
                                <span>{item.my_rate ? item.my_rate.toFixed(3) : '-'}</span>
                                {formatLamp(item.my_lamp) && (
                                  <span className="text-[10px] bg-white text-gray-700 px-1 py-0.5 rounded border border-gray-300 shadow-sm leading-none font-sans font-medium tracking-tight">
                                    {formatLamp(item.my_lamp)}
                                  </span>
                                )}
                              </div>
                            </td>
                            {!isWeapons && <td className="px-3 py-2 whitespace-nowrap text-sm font-medium text-blue-600 font-mono">
                              {item.expected_rate ? item.expected_rate.toFixed(3) : '-'}
                            </td>}
                            <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-700 font-mono">
                              {item.my_ts ? item.my_ts.toLocaleString() : '-'}
                            </td>
                            {!isWeapons && <td className="px-3 py-2 whitespace-nowrap text-sm font-mono font-bold text-indigo-600">
                              {item.target_score ? item.target_score.toLocaleString() : '-'}
                            </td>}
                          </>
                        )}
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-600">
                          <div className="flex items-center gap-2">
                            <span>{(rateVal * 100).toFixed(1)}%</span>
                            <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                              <div 
                                className={`h-full ${rateVal > 0.4 ? 'bg-green-500' : rateVal > 0.2 ? 'bg-blue-500' : 'bg-red-400'}`}
                                style={{ width: `${rateVal * 100}%` }}
                              />
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {sortedItems.length === 0 && (
                    <tr>
                      <td colSpan={isPs ? 7 : isRank ? 7 : (isWeapons ? 7 : 9)} className="px-3 py-8 text-center text-sm text-gray-500">
                        該当する楽曲がありません。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </main>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
