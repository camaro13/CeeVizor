import './HeapGraph.css';

function HeapGraph({ heap }) {
  if (!heap || heap.length === 0) return null;

  return (
    <div className="heap-graph">
      {heap.map((block, idx) => (
        <div className="heap-block" key={idx}>
          {block.label} = {block.value}
        </div>
      ))}
    </div>
  );
}

export default HeapGraph;
