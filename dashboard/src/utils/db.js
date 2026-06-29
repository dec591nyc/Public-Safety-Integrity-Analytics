import { Pool } from 'pg';

const connectionString = process.env.PUBLIC_SAFETY_DATABASE_URL;

let pool = null;

if (connectionString) {
  pool = new Pool({
    connectionString,
    ssl: {
      rejectUnauthorized: false
    }
  });
}

export default pool;
