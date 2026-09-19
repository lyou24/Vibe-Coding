import React from 'react';
import { toPng } from 'html-to-image';

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

interface ExportControlsProps {
  items: RecommendItem[];
  activeTab: string;
  tableId: string;
  groupLabel?: string;
}

const tabNames: Record<string, string> = {
  'new': '新曲枠',
  'best': 'ベスト枠',
  'ps': 'Pスコア枠',
  'weapons': '逆リコメンド',
  'similar': '類似プレイヤー',
  'rank': '目標達成',
  'mydata': 'マイデータ'
};

const ExportControls: React.FC<ExportControlsProps> = ({ items, activeTab, tableId, groupLabel }) => {
  const handleCopyMarkdown = () => {
    const isPs = activeTab === 'ps';
    const isWeapons = activeTab === 'weapons';
    const isRank = activeTab === 'rank';
    let markdown = '';

    if (isPs) {
      markdown += '| # | タイトル | 難易度 | 譜面定数 | 現在の星 | 目標の星 | 目標達成時レート | 採用率 |\n';
      markdown += '|---|---|---|---|---|---|---|---|\n';
    } else if (isRank) {
      markdown += '| # | タイトル | 難易度 | 譜面定数 | 現在TS (ランプ) | 目標 | 目標まで | 達成率 |\n';
      markdown += '|---|---|---|---|---|---|---|---|\n';
    } else {
      markdown += `| # | タイトル | 難易度 | 譜面定数 | 現在レート | ${!isWeapons ? '目標レート | ' : ''}現在TS | ${!isWeapons ? '目標TS | ' : ''}採用率 |\n`;
      let sep = '|---|---|---|---|---|';
      if (!isWeapons) sep += '---|---|';
      else sep += '---|';
      markdown += sep + '---|\n';
    }

    items.forEach((item, idx) => {
      const diff = item.key.split('_')[1];
      const adopt = ((isRank ? (item.achievement_rate ?? 0) : item.adopt_rate) * 100).toFixed(1) + '%';
      
      let row = `| ${idx + 1} | ${item.title} | ${diff} | ${item.constant.toFixed(1)} | `;
      
      if (isPs) {
        const myStarLamp = `${item.my_star ?? 0}${item.my_lamp ? ' ' + item.my_lamp : ''}`;
        const targetStar = item.target_star ?? '-';
        const expectedRate = item.expected_rate ? item.expected_rate.toFixed(3) : '-';
        row += `${myStarLamp} | ${targetStar} | ${expectedRate} | ${adopt} |`;
      } else if (isRank) {
        const myTsLamp = `${item.my_ts ? item.my_ts.toLocaleString() : '-'}${item.my_lamp ? ' (' + item.my_lamp + ')' : ''}`;
        const targetStr = item.target_score
          ? `${item.target_score.toLocaleString()} (${item.target_rank})`
          : `${item.target_rank}`;
        const diffText = item.diff_to_target !== undefined ? `あと ${item.diff_to_target.toLocaleString()} 点` : '-';
        row += `${myTsLamp} | ${targetStr} | ${diffText} | ${adopt} |`;
      } else {
        const myRateLamp = `${item.my_rate ? item.my_rate.toFixed(3) : '-'}${item.my_lamp ? ' ' + item.my_lamp : ''}`;
        const expectedRate = item.expected_rate ? item.expected_rate.toFixed(3) : '-';
        const myTs = item.my_ts ? item.my_ts.toLocaleString() : '-';
        const targetTs = item.target_score ? item.target_score.toLocaleString() : '-';
        
        row += `${myRateLamp} | `;
        if (!isWeapons) row += `${expectedRate} | `;
        row += `${myTs} | `;
        if (!isWeapons) row += `${targetTs} | `;
        row += `${adopt} |`;
      }
      markdown += row + '\n';
    });

    navigator.clipboard.writeText(markdown).then(() => {
      alert('Markdown copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy text: ', err);
    });
  };

  const handleDownloadImage = () => {
    const tableElement = document.getElementById(tableId);
    if (!tableElement) return;
    
    // 一時的なヘッダー要素を作成して追加
    const headerDiv = document.createElement('div');
    headerDiv.style.padding = '16px';
    headerDiv.style.backgroundColor = '#ffffff';
    headerDiv.style.borderBottom = '2px solid #e5e7eb';
    headerDiv.style.marginBottom = '8px';
    headerDiv.style.fontFamily = 'sans-serif';
    
    const titleObj = document.createElement('h2');
    titleObj.innerText = `Ongeki Target Finder - ${tabNames[activeTab] || activeTab}`;
    titleObj.style.fontSize = '20px';
    titleObj.style.fontWeight = 'bold';
    titleObj.style.color = '#1f2937';
    titleObj.style.margin = '0 0 4px 0';
    headerDiv.appendChild(titleObj);
    
    if (groupLabel) {
      const subObj = document.createElement('p');
      subObj.innerText = `比較対象: ${groupLabel}`;
      subObj.style.fontSize = '14px';
      subObj.style.color = '#6b7280';
      subObj.style.margin = '0';
      headerDiv.appendChild(subObj);
    }
    
    // tableの親要素(通常はラッパーのdiv)にヘッダーを挿入し、親要素ごとキャプチャする
    const parentContainer = tableElement.parentElement;
    if (parentContainer) {
      parentContainer.insertBefore(headerDiv, tableElement);
      
      toPng(parentContainer, { backgroundColor: '#ffffff', pixelRatio: 2, skipFonts: true })
        .then(function (dataUrl) {
          parentContainer.removeChild(headerDiv); // 撮影後に削除
          
          const link = document.createElement('a');
          link.download = `recommend_${activeTab}.png`;
          link.href = dataUrl;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        })
        .catch(function (error) {
          parentContainer.removeChild(headerDiv); // エラー時も削除
          console.error('Failed to export PNG', error);
          alert('Failed to export PNG');
        });
    } else {
      // 親がない場合はtableのみ(フォールバック)
      toPng(tableElement, { backgroundColor: '#ffffff', pixelRatio: 2, skipFonts: true })
        .then(function (dataUrl) {
          const link = document.createElement('a');
          link.download = `recommend_${activeTab}.png`;
          link.href = dataUrl;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        })
        .catch(function (error) {
          console.error('Failed to export PNG', error);
          alert('Failed to export PNG');
        });
    }
  };

  return (
    <div className="flex gap-2 ml-auto">
      <button 
        onClick={handleCopyMarkdown}
        className="px-3 py-1 bg-white/20 hover:bg-white/30 text-white rounded text-sm shadow-sm font-medium transition-colors border border-white/30"
      >
        Copy Markdown
      </button>
      <button 
        onClick={handleDownloadImage}
        className="px-3 py-1 bg-white/20 hover:bg-white/30 text-white rounded text-sm shadow-sm font-medium transition-colors border border-white/30"
      >
        Download PNG
      </button>
    </div>
  );
};

export default ExportControls;
