import { Queue, Worker } from 'bullmq';
import { Redis } from 'ioredis';

const connection = new Redis(process.env.REDIS_URL || 'redis://localhost:6379');

// Contoh queue untuk tugas berat, misalnya pemrosesan laporan
export const reportQueue = new Queue('report-queue', { connection });

// Worker untuk memproses job dari queue
export const reportWorker = new Worker('report-queue', async job => {
    console.log(`Memproses laporan: ${job.id}`);
    // TODO: Implementasikan pemrosesan laporan sesuai kebutuhan
    await new Promise(resolve => setTimeout(resolve, 5000)); // simulasi tugas berat
    console.log(`Selesai memproses laporan: ${job.id}`);
}, { connection });

reportWorker.on('failed', (job, err) => {
    console.error(`Job ${job?.id} gagal:`, err);
});

export default { reportQueue, reportWorker };
