import React from 'react';
import './DataGraph.css';

function DataGraph({ data = [] }) {
  if (!data || data.length === 0) return null;

  // 여러 값이 필요하면 map, 하나만 있으면 단일 출력
  return (
    <div className="data-graph">
      {data[0] && (
        <div className="data-variable">
          {data[0].key} = {data[0].value}
        </div>
      )}
    </div>
  );
}

export default DataGraph;
